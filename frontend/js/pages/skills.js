// Skills management page
const SkillsPage = {
    render() {
        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading">Loading skills...</div>';

        this.loadSkills();
    },

    async loadSkills() {
        const content = DOM.$('#page-content');

        try {
            const skills = await API.get('/api/skills');
            const categories = await API.get('/api/skills/categories');

            content.innerHTML = `
            <div class="skills-page">
                <div class="page-header-actions">
                    <h1>Skills Management</h1>
                    <div class="actions">
                        <button class="btn btn-secondary" onclick="SkillsPage.importSkill()">
                            <i data-lucide="upload"></i> Import Skill
                        </button>
                        <button class="btn btn-primary" onclick="SkillsPage.createSkill()">
                            <i data-lucide="plus"></i> Create Skill
                        </button>
                    </div>
                </div>

                <div class="skills-filters">
                    <select id="category-filter" onchange="SkillsPage.filterSkills()">
                        <option value="">All Categories</option>
                        ${categories.categories.map(cat => `<option value="${cat}">${cat}</option>`).join('')}
                    </select>
                    <label>
                        <input type="checkbox" id="builtin-filter" onchange="SkillsPage.filterSkills()">
                        Show Built-in Only
                    </label>
                    <label>
                        <input type="checkbox" id="enabled-filter" checked onchange="SkillsPage.filterSkills()">
                        Enabled Only
                    </label>
                </div>

                <div class="skills-grid" id="skills-grid">
                    ${skills.map(skill => SkillsPage.renderSkillCard(skill)).join('')}
                </div>
            </div>
        `;

            DOM.createIcons();
        } catch (error) {
            console.error('Error loading skills:', error);
            content.innerHTML = `
                <div class="error-state">
                    <h3>Error loading skills</h3>
                    <p>${error.message}</p>
                    <button class="btn btn-primary" onclick="SkillsPage.loadSkills()">Retry</button>
                </div>
            `;
        }
    },

    renderSkillCard(skill) {
        const statusClass = skill.is_enabled ? 'enabled' : 'disabled';
        const builtinBadge = skill.is_builtin ? '<span class="badge badge-builtin">Built-in</span>' : '';

        return `
            <div class="skill-card ${statusClass}" data-skill-id="${skill.id}">
                <div class="skill-card-header">
                    <h3>${skill.name}</h3>
                    ${builtinBadge}
                </div>
                <div class="skill-card-body">
                    <p class="skill-description">${skill.description}</p>
                    <div class="skill-meta">
                        <span class="skill-category">${skill.category || 'general'}</span>
                        <span class="skill-version">v${skill.version}</span>
                    </div>
                    <div class="skill-tags">
                        ${(skill.tags || []).map(tag => `<span class="tag">${tag}</span>`).join('')}
                    </div>
                    <div class="skill-permissions">
                        ${(skill.permissions || []).map(perm => `<span class="permission">${perm}</span>`).join('')}
                    </div>
                </div>
                <div class="skill-card-actions">
                    <button class="btn btn-sm" onclick="SkillsPage.viewSkill('${skill.id}')">
                        <i data-lucide="eye"></i> View
                    </button>
                    <button class="btn btn-sm" onclick="SkillsPage.testSkill('${skill.id}')">
                        <i data-lucide="play"></i> Test
                    </button>
                    <button class="btn btn-sm" onclick="SkillsPage.exportSkill('${skill.id}')">
                        <i data-lucide="download"></i> Export
                    </button>
                    ${!skill.is_builtin ? `
                        <button class="btn btn-sm btn-danger" onclick="SkillsPage.deleteSkill('${skill.id}')">
                            <i data-lucide="trash"></i> Delete
                        </button>
                    ` : ''}
                    <label class="toggle-switch">
                        <input type="checkbox" ${skill.is_enabled ? 'checked' : ''}
                               onchange="SkillsPage.toggleSkill('${skill.id}', this.checked)">
                        <span class="toggle-slider"></span>
                    </label>
                </div>
            </div>
        `;
    },

    async filterSkills() {
        const category = document.getElementById('category-filter').value;
        const builtinOnly = document.getElementById('builtin-filter').checked;
        const enabledOnly = document.getElementById('enabled-filter').checked;

        let url = '/api/skills?';
        if (category) url += `category=${category}&`;
        if (builtinOnly) url += `is_builtin=true&`;
        if (enabledOnly) url += `is_enabled=true&`;

        try {
            const skills = await API.get(url);
            document.getElementById('skills-grid').innerHTML =
                skills.map(skill => SkillsPage.renderSkillCard(skill)).join('');
            DOM.createIcons();
        } catch (error) {
            Toast.error('Failed to filter skills');
        }
    },

    async viewSkill(skillId) {
        try {
            const skill = await API.get(`/api/skills/${skillId}`);

            Modal.show({
                title: skill.name,
                content: `
                    <div class="skill-details">
                        <p><strong>ID:</strong> ${skill.id}</p>
                        <p><strong>Version:</strong> ${skill.version}</p>
                        <p><strong>Category:</strong> ${skill.category || 'N/A'}</p>
                        <p><strong>Description:</strong> ${skill.description}</p>

                        <h4>Parameters:</h4>
                        <ul>
                            ${skill.parameters.map(p => `
                                <li><strong>${p.name}</strong> (${p.type}${p.required ? ', required' : ''}): ${p.description}</li>
                            `).join('')}
                        </ul>

                        <h4>Permissions:</h4>
                        <ul>
                            ${skill.permissions.map(p => `<li>${p}</li>`).join('')}
                        </ul>

                        <h4>Code:</h4>
                        <pre><code>${skill.code}</code></pre>
                    </div>
                `,
                size: 'large'
            });
        } catch (error) {
            Toast.error('Failed to load skill details');
        }
    },

    async testSkill(skillId) {
        try {
            const skill = await API.get(`/api/skills/${skillId}`);

            // Load datasources and knowledge bases for dropdowns
            let datasources = [];
            let knowledgeBases = [];
            try {
                datasources = await API.get('/api/datasources');
                knowledgeBases = await API.get('/api/knowledge-bases');
            } catch (e) {
                console.error('Failed to load datasources/KBs:', e);
            }

            // Generate input fields based on parameter type
            const paramInputs = await Promise.all(skill.parameters.map(async p => {
                let inputHtml = '';

                // Special handling for datasource_id
                if (p.name === 'datasource_id' && p.type === 'integer') {
                    const options = datasources.map(ds =>
                        `<option value="${ds.id}">${ds.name} (${ds.db_type})</option>`
                    ).join('');
                    inputHtml = `
                        <div class="form-group">
                            <label>${p.name} ${p.required ? '*' : ''}</label>
                            <select id="param-${p.name}" class="form-control">
                                <option value="">-- Select Datasource --</option>
                                ${options}
                            </select>
                            <small class="form-text">${p.description}</small>
                        </div>
                    `;
                }
                // Special handling for kb_ids (array of integers)
                else if (p.name === 'kb_ids' && p.type === 'array') {
                    const options = knowledgeBases.map(kb =>
                        `<option value="${kb.id}">${kb.name}</option>`
                    ).join('');
                    inputHtml = `
                        <div class="form-group">
                            <label>${p.name} ${p.required ? '*' : ''}</label>
                            <select id="param-${p.name}" class="form-control" multiple style="height: 100px;">
                                ${options}
                            </select>
                            <small class="form-text">${p.description} (Hold Ctrl/Cmd to select multiple)</small>
                        </div>
                    `;
                }
                // Boolean type
                else if (p.type === 'boolean') {
                    inputHtml = `
                        <div class="form-group">
                            <label>${p.name} ${p.required ? '*' : ''}</label>
                            <select id="param-${p.name}" class="form-control">
                                <option value="">-- Select --</option>
                                <option value="true">true</option>
                                <option value="false">false</option>
                            </select>
                            <small class="form-text">${p.description}</small>
                        </div>
                    `;
                }
                // Default text input for other types
                else {
                    const placeholder = p.type === 'array' || p.type === 'object'
                        ? `${p.description} (JSON format)`
                        : p.description;
                    inputHtml = `
                        <div class="form-group">
                            <label>${p.name} ${p.required ? '*' : ''}</label>
                            <input type="text" id="param-${p.name}" class="form-control" placeholder="${placeholder}" value="${p.default || ''}">
                            <small class="form-text">${p.description}</small>
                        </div>
                    `;
                }

                return inputHtml;
            }));

            Modal.show({
                title: `Test ${skill.name}`,
                content: `
                    <form id="test-skill-form">
                        ${paramInputs.join('')}
                        <button type="submit" class="btn btn-primary">Execute</button>
                    </form>
                    <div id="test-result" style="margin-top: 20px;"></div>
                `,
                size: 'large'
            });

            document.getElementById('test-skill-form').onsubmit = async (e) => {
                e.preventDefault();
                const params = {};
                skill.parameters.forEach(p => {
                    const element = document.getElementById(`param-${p.name}`);
                    let value = null;

                    // Handle multi-select for kb_ids
                    if (p.name === 'kb_ids' && element.multiple) {
                        const selectedOptions = Array.from(element.selectedOptions);
                        if (selectedOptions.length > 0) {
                            value = selectedOptions.map(opt => parseInt(opt.value));
                            params[p.name] = value;
                        }
                    } else {
                        value = element.value;
                        if (value) {
                            if (p.type === 'integer') {
                                params[p.name] = parseInt(value);
                            } else if (p.type === 'boolean') {
                                params[p.name] = value === 'true';
                            } else if (p.type === 'array' || p.type === 'object') {
                                try {
                                    params[p.name] = JSON.parse(value);
                                } catch (e) {
                                    Toast.error(`Invalid JSON for parameter ${p.name}`);
                                    throw e;
                                }
                            } else {
                                params[p.name] = value;
                            }
                        }
                    }
                });

                const resultDiv = document.getElementById('test-result');
                resultDiv.innerHTML = '<p>Executing...</p>';

                try {
                    const result = await API.post(`/api/skills/${skillId}/test`, {
                        skill_id: skillId,
                        parameters: params
                    });

                    resultDiv.innerHTML = `
                        <h4>Result:</h4>
                        <pre><code>${JSON.stringify(result, null, 2)}</code></pre>
                    `;
                } catch (error) {
                    resultDiv.innerHTML = `<p class="error">Error: ${error.message}</p>`;
                }
            };
        } catch (error) {
            Toast.error('Failed to load skill');
        }
    },

    async exportSkill(skillId) {
        window.location.href = `/api/skills/${skillId}/export`;
    },

    async toggleSkill(skillId, enabled) {
        try {
            await API.put(`/api/skills/${skillId}`, { is_enabled: enabled });
            Toast.success(`Skill ${enabled ? 'enabled' : 'disabled'}`);
        } catch (error) {
            Toast.error('Failed to toggle skill');
        }
    },

    async deleteSkill(skillId) {
        if (!confirm('Are you sure you want to delete this skill?')) return;

        try {
            await API.delete(`/api/skills/${skillId}`);
            Toast.success('Skill deleted');
            this.loadSkills();
        } catch (error) {
            Toast.error('Failed to delete skill');
        }
    },

    async importSkill() {
        Modal.show({
            title: 'Import Skill',
            content: `
                <form id="import-skill-form">
                    <div class="form-group">
                        <label>YAML File</label>
                        <input type="file" id="skill-file" accept=".yaml,.yml" required>
                    </div>
                    <button type="submit" class="btn btn-primary">Import</button>
                </form>
            `
        });

        document.getElementById('import-skill-form').onsubmit = async (e) => {
            e.preventDefault();
            const file = document.getElementById('skill-file').files[0];

            const formData = new FormData();
            formData.append('file', file);

            try {
                const token = localStorage.getItem('auth_token');
                const headers = {};
                if (token) headers['Authorization'] = `Bearer ${token}`;

                const response = await fetch('/api/skills/import', {
                    method: 'POST',
                    headers,
                    body: formData
                });

                if (!response.ok) {
                    const err = await response.json().catch(() => ({ detail: response.statusText }));
                    throw new Error(err.detail || 'Import failed');
                }

                Toast.success('Skill imported successfully');
                Modal.hide();
                SkillsPage.loadSkills();
            } catch (error) {
                Toast.error('Failed to import skill: ' + error.message);
            }
        };
    },

    createSkill() {
        Toast.info('Skill creation UI coming soon. Use import for now.');
    }
};

// Register page
window.SkillsPage = SkillsPage;
