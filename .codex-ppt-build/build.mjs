import fs from 'node:fs/promises';
import path from 'node:path';
import { Presentation, PresentationFile } from '@oai/artifact-tool';
import { finalizePresentation } from '/Users/william/.codex/plugins/cache/openai-primary-runtime/presentations/26.1017.22136/skills/presentations/container_tools/artifact_tool_utils.mjs';

const ROOT='/Users/william/prog/dbclaw';
const BUILD=path.join(ROOT,'.codex-ppt-build');
const SKILL='/Users/william/.codex/plugins/cache/openai-primary-runtime/presentations/26.1017.22136/skills/presentations';
const FONT='Hiragino Sans GB';
const C={ink:'#142D48',muted:'#586B80',blue:'#1167C5',teal:'#087F8C',line:'#D7E2ED',pale:'#F0F5FA',navy:'#102E4E',white:'#FFFFFF'};
const p=Presentation.create({slideSize:{width:1600,height:900}});
const s=p.slides.add();
s.background.fill=C.white;
function rect(name,x,y,w,h,fill,stroke='none',sw=0){return s.shapes.add({name,geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:stroke,width:sw,style:'solid'}});}
function txt(name,text,x,y,w,h,size=26,color=C.ink,bold=false,align='left'){
 const sh=rect(name,x,y,w,h,'none'); sh.text=text;
 sh.text.style={typeface:FONT,fontSize:size,color,bold,alignment:align,verticalAlignment:'middle',wrap:'none',autoFit:'none',insets:0};
 return sh;
}
function rule(name,x,y,w,color=C.line){return s.shapes.add({name,geometry:'line',position:{left:x,top:y,width:w,height:0},fill:'none',line:{fill:color,width:1.4,style:'solid'}});}
function vertical(name,x,y,h,color=C.line){return s.shapes.add({name,geometry:'line',position:{left:x,top:y,width:0,height:h},fill:'none',line:{fill:color,width:1.2,style:'solid'}});}
function layer(label,sub,y,h,fill=C.pale,dark=false){
 const bg=rect(label+'层',58,y,1484,h,fill);
 txt(label+'标签',label,86,y+20,172,36,27,dark?C.white:C.ink,true);
 if(sub)txt(label+'说明',sub,86,y+58,172,30,22,dark?'#B7D0E8':C.muted);
 vertical(label+'分隔',266,y+20,h-40,dark?'#3D5A76':C.line);
 return bg;
}

txt('标题','DBClaw 功能架构',62,36,1150,76,54,C.ink,true);
txt('副标题','AI 原生数据库智能卫士，统一监控、诊断、巡检与告警',64,112,1460,40,28,C.muted);

// Five horizontal layers form one editable functional architecture.
layer('访问与协作','面向 DBA / SRE',177,100);
txt('控制台入口','Web 控制台',300,190,285,35,28,C.ink,true);
txt('控制台入口说明','资源总览与实例工作台',300,230,310,29,24,C.muted);
txt('机器人入口','机器人对话',700,190,260,35,28,C.ink,true);
txt('机器人入口说明','飞书、钉钉、微信',700,230,310,29,24,C.muted);
txt('通知出口','通知分发',1100,190,330,35,28,C.ink,true);
txt('通知出口说明','Webhook、邮件、企业 IM',1100,230,400,29,24,C.muted);

layer('运维功能','日常运维与排障',295,136,'#F7F9FC');
const features=[
 ['监控看板','数据库与主机指标','实时状态与历史趋势'],
 ['AI 智能诊断','SQL、会话与锁分析','根因判断与处置建议'],
 ['自动巡检','定时与事件触发','结构化巡检报告'],
 ['告警管理','阈值与 AI 判警','去重、恢复与通知'],
 ['知识库','文档检索与上下文','运维经验复用'],
];
features.forEach((f,i)=>{
 const x=300+i*245;
 txt('功能'+i,f[0],x,309,231,40,28,C.blue,true);
 txt('功能描述'+i,f[1],x,354,231,29,23,C.muted);
 txt('功能结果'+i,f[2],x,388,231,29,23,C.muted);
 if(i<4)vertical('功能分隔'+i,x+228,322,80);
});

layer('AI 能力引擎','AI Agent 编排',449,161,C.navy,true);
const steps=['意图识别','上下文构建','技能调用','证据分析'];
const nodes=steps.map((t,i)=>txt('Agent步骤'+i,t,305+i*300,470,230,46,31,C.white,true,'center'));
for(let i=0;i<3;i++)s.shapes.connect(nodes[i],nodes[i+1],{kind:'straight',fromSide:'right',toSide:'left',line:{fill:'#6BC4D3',width:2},tail:{type:'triangle',width:'sm',length:'sm'}});
rule('AI引擎内部层线',300,533,1200,'#3D5A76');
txt('技能支撑','YAML 技能系统',309,553,338,35,26,'#C7DDF0');
txt('知识支撑','实例、指标与知识上下文',673,553,410,35,26,'#C7DDF0');
txt('模型支撑','OpenAI / Anthropic 兼容接口',1100,553,415,35,25,'#C7DDF0');

layer('采集与接入','统一资源连接',628,135);
txt('数据库连接','数据库连接器',300,643,720,34,27,C.teal,true);
txt('数据库资源第一行','MySQL、PostgreSQL、Oracle、SQL Server',300,685,730,30,24,C.muted);
txt('数据库资源第二行','openGauss、OceanBase MySQL、SAP HANA',300,723,750,29,24,C.muted);
vertical('数据库主机分隔',1030,650,88);
txt('主机连接','SSH 主机采集',1060,643,260,34,27,C.teal,true);
txt('主机资源','CPU、内存',1060,685,220,30,24,C.muted);
txt('主机资源第二行','磁盘、网络',1060,723,220,29,24,C.muted);
vertical('主机云分隔',1281,650,88);
txt('云监控接入','云监控集成',1310,643,225,34,27,C.teal,true);
txt('云厂商一','阿里云、腾讯云',1310,685,228,30,24,C.muted);
txt('云厂商二','华为云',1310,723,220,29,24,C.muted);

layer('平台支撑','运行与治理',781,79,'#F7F9FC');
// This shorter layer keeps only one label line and a single supporting line.
s.shapes.items.find(sh=>sh.name==='平台支撑说明').text='';
txt('服务框架','FastAPI 服务',300,802,210,34,25,C.ink,true);
txt('调度','任务调度',555,802,170,34,25,C.ink,true);
txt('权限','用户与技能权限',754,802,240,34,25,C.ink,true);
txt('持久化','PostgreSQL / 可选 TimescaleDB',1030,792,488,30,23,C.ink,true);
txt('部署','源码或 Docker 部署',1030,827,480,26,22,C.muted);

s.speakerNotes.text=[
 'DBClaw 面向 DBA、SRE 和研发团队，提供多数据库的监控、AI 诊断、自动巡检、告警与知识增强。该图按功能依赖关系分层，内部箭头表示 Agent 的诊断流程。',
 '监控持续采集数据库和关联主机指标。巡检支持定时及事件触发。告警覆盖阈值与 AI 判警、事件去重、自动恢复和通知。AI Agent 结合实例指标、历史记录、知识文档及可扩展 YAML 技能执行诊断并输出证据与建议。',
 '模型层支持 OpenAI 与 Anthropic 兼容协议。未配置模型时，基础监控等非 AI 能力仍可运行。PostgreSQL 保存元数据与监控历史，TimescaleDB 为可选时序扩展。',
 '依据本地项目当前文档和源码核对。参考：/Users/william/prog/dbclaw/README_CN.md，/Users/william/prog/dbclaw/README.md，/Users/william/prog/dbclaw/docs/产品操作介绍文档.md，/Users/william/prog/dbclaw/backend/services/ai_agent.py，/Users/william/prog/dbclaw/backend/skills/executor.py，/Users/william/prog/dbclaw/backend/services/db_connector.py。',
 '数据库清单以当前 README 与连接器实现为准。云监控接入为阿里云、腾讯云、华为云。机器人对话和通知渠道分别表达，不将企业微信通知等同于对话机器人。'
].join('\n\n');
await fs.writeFile(path.join(BUILD,'slide-01.png'),new Uint8Array(await (await p.export({slide:s,format:'png',scale:1})).arrayBuffer()));
await fs.writeFile(path.join(BUILD,'slide-01.layout.json'),await (await s.export({format:'layout'})).text());
const candidatePath=path.join(BUILD,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(candidatePath);
const result=await finalizePresentation({
 workspaceDir:ROOT,candidatePath,finalPath:path.join(ROOT,'outputs','DBClaw_功能架构.pptx'),
 explicitTotalSlideCount:1,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
 pythonExecutable:'/Users/william/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',
 integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','15240000,8572500','--validate-bullet-geometry','--validate-heading-fit'],
 fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,
 receiptPath:path.join(BUILD,'validation.json')
});
console.log(JSON.stringify(result));
