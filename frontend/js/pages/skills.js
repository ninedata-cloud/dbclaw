// Skills management page
const SkillsPage = {
    _categories: [],

    async render() {
        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading">Loading skills...</div>';

        try {
            const [skills, categoriesRes] = await Promise.all([
                API.get('/api/skills?is_enabled=true'),
                API.get('/api/skills/categories')
            ]);
            this._categories = categoriesRes.categories || [];

            Header.render('技能管理', this._buildHeaderActions());
            this._renderGrid(content, skills);
        } catch (error) {
            console.error('Error loading skills:', error);
            content.innerHTML = `
                <div class="error-state">
                    <h3>Error loading skills</h3>
                    <p>${error.message}</p>
                    <button class="btn btn-primary" onclick="SkillsPage.render()">Retry</button>
                </div>
            `;
        }
    },

    _buildHeaderActions() {
        const filters = DOM.el('div', { className: 'dashboard-filters' });
        filters.innerHTML = `
            <div style=\"position:relative;display:flex;align-items:center;\">
                <i data-lucide=\"search\" style=\"position:absolute;left:8px;width:14px;height:14px;color:var(--text-secondary);pointer-events:none;z-index:1;\"></i>
                <input type=\"text\" id=\"search-input\" class=\"filter-input\"
                       placeholder=\"搜索名称、标签、描述...\"
                       style=\"padding-left:28px;min-width:200px;\"
                       onkeyup=\"SkillsPage.handleSearch(event)\">
            </div>
            <select id=\"category-filter\" class=\"filter-select\" onchange=\"SkillsPage.filterSkills()\">
                <option value=\"\">全部分类</option>
                ${this._categories.map(cat => `<option value=\"${cat}\">${cat}</option>`).join('')}
            </select>
            <label class=\"filter-checkbox\">
                <input type=\"checkbox\" id=\"builtin-filter\" onchange=\"SkillsPage.filterSkills()\"> 仅内置
            </label>
            <label class=\"filter-checkbox\">
                <input type=\"checkbox\" id=\"enabled-filter\" checked onchange=\"SkillsPage.filterSkills()\"> 已启用
            </label>
        `;

        const importBtn = DOM.el('button', { className: 'btn btn-secondary' });
        importBtn.innerHTML = '<i data-lucide=\"upload\"></i> 导入';
        importBtn.onclick = () => SkillsPage.importSkill();

        const createBtn = DOM.el('button', { className: 'btn btn-primary' });
        createBtn.innerHTML = '<i data-lucide=\"plus\"></i> 创建技能';
        createBtn.onclick = () => SkillsPage.createSkill();

        setTimeout(() => DOM.createIcons(), 0);
        return [filters, importBtn, createBtn];
    },

    _renderGrid(content, skills) {
        content.innerHTML = `
            <div class=\"skills-page\">
                <div class=\"skills-grid\" id=\"skills-grid\">
                    ${skills.map(skill => SkillsPage.renderSkillCard(skill)).join('')}
                </div>
            </div>
        `;
        DOM.createIcons();
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
                    ${!skill.is_builtin ? `
                        <button class="btn btn-sm" onclick="SkillsPage.editSkill('${skill.id}')">
                            <i data-lucide="edit"></i> Edit
                        </button>
                    ` : ''}
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

    handleSearch(event) {
        // Debounce search to avoid too many API calls
        clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => {
            this.performSearch();
        }, 300);
    },

    async performSearch() {
        const searchQuery = document.getElementById('search-input').value.trim();

        if (!searchQuery) {
            // If search is empty, reload with filters
            this.filterSkills();
            return;
        }

        try {
            const skills = await API.get(`/api/skills/search?q=${encodeURIComponent(searchQuery)}`);
            document.getElementById('skills-grid').innerHTML =
                skills.map(skill => SkillsPage.renderSkillCard(skill)).join('');
            DOM.createIcons();
        } catch (error) {
            Toast.error('Search failed');
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
                        <p><strong>版本:</strong> ${skill.version}</p>
                        <p><strong>分类:</strong> ${skill.category || 'N/A'}</p>
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
            Toast.error('加载失败 skill details');
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
                console.error('加载数据源失败/KBs:', e);
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
                            <select id="param-${p.name}" class="form-control" style="min-width: 400px;">
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

            const testSkillForm = document.getElementById('test-skill-form');
            DOM.bindAsyncSubmit(testSkillForm, async () => {
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
            });
        } catch (error) {
            Toast.error('加载失败 skill');
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
        if (!confirm('确认操作 you want to delete this skill?')) return;

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

        const importSkillForm = document.getElementById('import-skill-form');
        DOM.bindAsyncSubmit(importSkillForm, async () => {
            const file = document.getElementById('skill-file').files[0];

            const formData = new FormData();
            formData.append('file', file);

            try {
                const response = await fetch('/api/skills/import', {
                    method: 'POST',
                    credentials: 'same-origin',
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
        });
    },

    async createSkill() {
        Modal.show({
            title: 'Create New Skill',
            content: `
                <form id="create-skill-form">
                    <div class="form-group">
                        <label>Skill ID *</label>
                        <input type="text" id="skill-id" class="form-control"
                               pattern="[a-z0-9_]+"
                               placeholder="e.g., my_custom_skill" required>
                        <small class="form-text">Lowercase letters, numbers, and underscores only</small>
                    </div>

                    <div class="form-group">
                        <label>Name *</label>
                        <input type="text" id="skill-name" class="form-control"
                               placeholder="e.g., My Custom Skill" required>
                    </div>

                    <div class="form-group">
                        <label>Version *</label>
                        <input type="text" id="skill-version" class="form-control"
                               pattern="\\d+\\.\\d+\\.\\d+"
                               placeholder="e.g., 1.0.0" value="1.0.0" required>
                        <small class="form-text">Semantic versioning (major.minor.patch)</small>
                    </div>

                    <div class="form-group">
                        <label>Category</label>
                        <input type="text" id="skill-category" class="form-control"
                               placeholder="e.g., diagnostics, monitoring">
                    </div>

                    <div class="form-group">
                        <label>Description *</label>
                        <textarea id="skill-description" class="form-control" rows="3"
                                  placeholder="Describe what this skill does" required></textarea>
                    </div>

                    <div class="form-group">
                        <label>Tags</label>
                        <input type="text" id="skill-tags" class="form-control"
                               placeholder="e.g., mysql, performance, slow-query (comma-separated)">
                    </div>

                    <div class="form-group">
                        <label>Permissions</label>
                        <div id="permissions-checkboxes" style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;">
                            <label><input type="checkbox" value="execute_query"> execute_query</label>
                            <label><input type="checkbox" value="execute_command"> execute_command</label>
                            <label><input type="checkbox" value="read_logs"> read_logs</label>
                            <label><input type="checkbox" value="modify_config"> modify_config</label>
                            <label><input type="checkbox" value="access_kb"> access_kb</label>
                            <label><input type="checkbox" value="read_datasource"> read_datasource</label>
                            <label><input type="checkbox" value="execute_any_sql"> execute_any_sql (危险)</label>
                            <label><input type="checkbox" value="execute_any_os_command"> execute_any_os_command (危险)</label>
                            <label><input type="checkbox" value="access_external_api"> access_external_api</label>
                            <label><input type="checkbox" value="admin"> admin</label>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Timeout (seconds)</label>
                        <input type="number" id="skill-timeout" class="form-control"
                               min="1" max="300" placeholder="Default: 30">
                        <small class="form-text">Maximum execution time (1-300 seconds)</small>
                    </div>

                    <div class="form-group">
                        <label>Parameters (JSON)</label>
                        <textarea id="skill-parameters" class="form-control" rows="6"
                                  placeholder='[{"name": "param1", "type": "string", "required": true, "description": "Parameter description"}]'>[]</textarea>
                        <small class="form-text">Array of parameter definitions</small>
                    </div>

                    <div class="form-group">
                        <label>Code *</label>
                        <textarea id="skill-code" class="form-control" rows="12"
                                  placeholder="async def execute(context, params):\n    # Your code here\n    return {'result': 'success'}" required></textarea>
                        <small class="form-text">Python async function code</small>
                    </div>

                    <div style="display: flex; gap: 10px; margin-top: 20px;">
                        <button type="submit" class="btn btn-primary">Create Skill</button>
                        <button type="button" class="btn btn-secondary" onclick="Modal.hide()">Cancel</button>
                    </div>
                </form>
            `,
            size: 'large'
        });

        const createSkillForm = document.getElementById('create-skill-form');
        DOM.bindAsyncSubmit(createSkillForm, async () => {
            try {
                // Collect form data
                const id = document.getElementById('skill-id').value.trim();
                const name = document.getElementById('skill-name').value.trim();
                const version = document.getElementById('skill-version').value.trim();
                const category = document.getElementById('skill-category').value.trim() || null;
                const description = document.getElementById('skill-description').value.trim();
                const tagsInput = document.getElementById('skill-tags').value.trim();
                const tags = tagsInput ? tagsInput.split(',').map(t => t.trim()).filter(t => t) : [];
                const timeout = document.getElementById('skill-timeout').value;
                const code = document.getElementById('skill-code').value.trim();

                // Collect permissions
                const permissions = Array.from(document.querySelectorAll('#permissions-checkboxes input:checked'))
                    .map(cb => cb.value);

                // Parse parameters JSON
                let parameters = [];
                const parametersInput = document.getElementById('skill-parameters').value.trim();
                if (parametersInput) {
                    try {
                        parameters = JSON.parse(parametersInput);
                        if (!Array.isArray(parameters)) {
                            throw new Error('Parameters must be an array');
                        }
                    } catch (e) {
                        Toast.error('Invalid parameters JSON: ' + e.message);
                        return;
                    }
                }

                // Build skill definition
                const skillDef = {
                    id,
                    name,
                    version,
                    category,
                    description,
                    tags,
                    parameters,
                    dependencies: [],
                    permissions,
                    code
                };

                if (timeout) {
                    skillDef.timeout = parseInt(timeout);
                }

                // Submit to API
                await API.post('/api/skills', {
                    skill: skillDef,
                    is_enabled: true
                });

                Toast.success('Skill created successfully');
                Modal.hide();
                SkillsPage.loadSkills();
            } catch (error) {
                Toast.error('Failed to create skill: ' + error.message);
            }
        });
    },

    async editSkill(skillId) {
        try {
            const skill = await API.get(`/api/skills/${skillId}`);

            Modal.show({
                title: `Edit Skill: ${skill.name}`,
                content: `
                    <form id="edit-skill-form">
                        <div class="form-group">
                            <label>Skill ID</label>
                            <input type="text" class="form-control" value="${skill.id}" disabled>
                            <small class="form-text">ID cannot be changed</small>
                        </div>

                        <div class="form-group">
                            <label>Name *</label>
                            <input type="text" id="edit-skill-name" class="form-control"
                                   value="${skill.name}" required>
                        </div>

                        <div class="form-group">
                            <label>Description *</label>
                            <textarea id="edit-skill-description" class="form-control" rows="3" required>${skill.description}</textarea>
                        </div>

                        <div class="form-group">
                            <label>Tags</label>
                            <input type="text" id="edit-skill-tags" class="form-control"
                                   value="${(skill.tags || []).join(', ')}"
                                   placeholder="comma-separated">
                        </div>

                        <div class="form-group">
                            <label>Parameters (JSON)</label>
                            <textarea id="edit-skill-parameters" class="form-control" rows="6">${JSON.stringify(skill.parameters || [], null, 2)}</textarea>
                            <small class="form-text">Array of parameter definitions</small>
                        </div>

                        <div class="form-group">
                            <label>Code *</label>
                            <textarea id="edit-skill-code" class="form-control" rows="12" required>${skill.code}</textarea>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="edit-skill-enabled" ${skill.is_enabled ? 'checked' : ''}>
                                Enabled
                            </label>
                        </div>

                        <div style="display: flex; gap: 10px; margin-top: 20px;">
                            <button type="submit" class="btn btn-primary">Save Changes</button>
                            <button type="button" class="btn btn-secondary" onclick="Modal.hide()">Cancel</button>
                        </div>
                    </form>
                `,
                size: 'large'
            });

            const editSkillForm = document.getElementById('edit-skill-form');
            DOM.bindAsyncSubmit(editSkillForm, async () => {
                try {
                    const name = document.getElementById('edit-skill-name').value.trim();
                    const description = document.getElementById('edit-skill-description').value.trim();
                    const tagsInput = document.getElementById('edit-skill-tags').value.trim();
                    const tags = tagsInput ? tagsInput.split(',').map(t => t.trim()).filter(t => t) : [];
                    const code = document.getElementById('edit-skill-code').value.trim();
                    const is_enabled = document.getElementById('edit-skill-enabled').checked;

                    let parameters = skill.parameters || [];
                    const parametersInput = document.getElementById('edit-skill-parameters').value.trim();
                    if (parametersInput) {
                        try {
                            parameters = JSON.parse(parametersInput);
                            if (!Array.isArray(parameters)) {
                                throw new Error('Parameters must be an array');
                            }
                        } catch (e) {
                            Toast.error('Invalid parameters JSON: ' + e.message);
                            return;
                        }
                    }

                    await API.put(`/api/skills/${skillId}`, {
                        name,
                        description,
                        tags,
                        parameters,
                        code,
                        is_enabled
                    });

                    Toast.success('Skill updated successfully');
                    Modal.hide();
                    SkillsPage.loadSkills();
                } catch (error) {
                    Toast.error('Failed to update skill: ' + error.message);
                }
            });
        } catch (error) {
            Toast.error('Failed to load skill: ' + error.message);
        }
    }
};

// Register page
window.SkillsPage = SkillsPage;
