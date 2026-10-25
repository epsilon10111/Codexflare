const assert = require('node:assert/strict');
const { test } = require('node:test');
const { EventEmitter } = require('node:events');
const { spawnSync } = require('node:child_process');
const vm = require('node:vm');
const path = require('node:path');

// Semantic fixture for the reviewed macOS build, using its exact patch anchors.
let fixture = `
function createWindow(e={}) {
  let n=(e.appearance??'primary')==='primary',r=n&&e.page;
  let {show:f=true,appearance:d='primary'}=e,S=this.saved,k=S?.isMaximized===true,
    A={width:480,height:600},F={contextIsolation:true,nodeIntegration:false},
    R={width:S?.width??1280,height:S?.height??820,x:S?.x,y:S?.y,show:f,
      minWidth:A?.width,minHeight:A?.height,webPreferences:F},z=new O.BrowserWindow(R);
  k&&z.once('ready-to-show',()=>z.maximize()); return z;
}
function syncPrimaryMinimumSize(){let e=this.windows;let t=this.getPrimaryMinimumSize();for(let n of e){if(n.setMinimumSize(t.width,t.height),n.isMaximized()||n.isFullScreen())continue;}}
function onboarding(n,t){let i=A5e(t);if((0,q.default)(this.primaryWindowMode,t)){};return i;}
function primary(e,t,n,r=false){const {background:backgroundLaunch=false}={background:r};return V.createPrimaryWindow({title:O.app.getName(),show:e,initialRoute:t===\`/\`?void 0:t,opener:n});}
async function load(z,n,r,e,p,P){return await z.loadURL(t.o(p,{mcpAppSandboxLocalDevelopment:P}));}
function protocols(){We.deepLinks.registerProtocolClient();}
`;
const renamed = JSON.parse(process.env.CODEXFLARE_TEST_BINDINGS || '{}');
fixture = fixture.replace(/\b[A-Za-z_$][\w$]*\b/g, token => renamed[token] || token);

const result = spawnSync(process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'), ['-c',
  'import json,sys; from tools.patch_macos import patch_main; s=sys.stdin.read(); print(json.dumps({m if muted else m+"-audio":patch_main(s,m,muted) for m in ("restore","centered","fullscreen") for muted in (True,False)}))'],
  {cwd:path.resolve(__dirname,'..'),input:fixture,encoding:'utf8'});
assert.equal(result.status,0,result.stderr);
const scripts=JSON.parse(result.stdout);
function harness(mode,saved=null,area={x:50,y:35,width:1400,height:900}) {
  class Window extends EventEmitter {
    constructor(options) { super(); this.options=options; this.visible=options.show; this.webContents=new EventEmitter(); this.gestures=[]; this.webContents.executeJavaScript=async (code,gesture)=>this.gestures.push({code,gesture}); }
    isDestroyed(){return false;} isVisible(){return this.visible;}
    isMaximized(){return !!this.maximized;} isFullScreen(){return !!this.fullscreen;}
    maximize(){this.maximized=true;} unmaximize(){this.maximized=false;} setBounds(bounds){Object.assign(this.options,bounds);} setFullScreen(value){this.fullscreen=value;}
    getBounds(){return this.options;} setMinimumSize(w,h){this.minimum={w,h};}
    async loadURL(url){this.url=url;}
  }
  const context=vm.createContext({O:{BrowserWindow:Window,app:{getName:()=> 'Codex'},
    screen:{getPrimaryDisplay:()=>({workArea:area}),getDisplayMatching:()=>({workArea:area})}},
    V:{getPrimaryWindow:()=>null,createPrimaryWindow:x=>x},URL,process:{env:{}},
    t:{o:()=> 'app://-/index.html'}, A5e:()=>({width:500,height:500}),q:{default:()=>false}});
  for (const [before,after] of Object.entries(renamed)) if (before in context) context[after]=context[before];
  vm.runInContext(scripts[mode],context);
  return {context,create:(options={})=>context.createWindow.call({saved},{codexflareStartup:true,...options})};
}

test('macOS restore retains saved size and maximization',()=>{
  const h=harness('restore',{x:80,y:50,width:980,height:720,isMaximized:true});const w=h.create();
  w.emit('ready-to-show');assert.equal(w.options.width,980);assert.equal(w.maximized,true);
  assert.equal(h.context.onboarding(w,'login'),null);
  assert.equal(w.options.webPreferences.contextIsolation,true);
  assert.equal(w.options.webPreferences.nodeIntegration,false);
});
test('macOS restore explicitly reapplies non-maximized saved bounds',()=>{
  const h=harness('restore',{x:210,y:80,width:980,height:720,isMaximized:false});
  const w=h.create();w.maximized=true;w.emit('ready-to-show');
  assert.equal(w.maximized,false);assert.equal(w.options.x,210);assert.equal(w.options.width,980);
});
test('macOS centered fits small displays and suppresses restored maximization',()=>{
  const h=harness('centered',{width:1600,height:1100,isMaximized:true},{x:0,y:25,width:800,height:550});
  const w=h.create();w.emit('ready-to-show');assert.equal(w.options.width,800);assert.equal(w.options.height,550);
  assert.equal(w.options.minHeight,550);assert.equal(w.maximized,undefined);
});
test('macOS fullscreen waits for a hidden window to show',()=>{
  const h=harness('fullscreen');const w=h.create({show:false});assert.equal(w.fullscreen,undefined);
  w.visible=true;w.emit('show');assert.equal(w.fullscreen,true);
});
test('auxiliary, detached and non-startup windows retain their geometry',()=>{
  for(const options of [{appearance:'avatarOverlay'},{page:true},{codexflareStartup:false}]){
    const w=harness('centered').create(options);assert.equal(w.codexflareWindowMode,undefined);assert.equal(w.options.width,1280);
  }
});
test('background launch remains hidden and is not tagged for animation',()=>{
  const {context}=harness('restore');const opts=context.primary(false,'/',null,true);
  assert.equal(opts.show,false);assert.equal(opts.codexflareStartup,false);
});
test('only a cold-start main window receives the animation URL flag',async()=>{
  const {context,create}=harness('restore');
  for(const [main,page,start,expected] of [[true,false,true,true],[false,false,true,false],[true,true,true,false],[true,false,false,false]]){
    const w=create();await context.load(w,main,page,{codexflareStartup:start},'/',false);
    assert.equal(new URL(w.url).searchParams.has('codexBootAnimation'),expected);
  }
  assert.doesNotThrow(()=>context.protocols());
});

test('macOS sound playback is authorized once, only for the startup main window',async()=>{
  const {context,create}=harness('restore-audio');
  const w=create();await context.load(w,true,false,{codexflareStartup:true},'/',false);
  assert.equal(w.webContents.listenerCount('did-finish-load'),1);
  w.webContents.emit('did-finish-load');w.webContents.emit('did-finish-load');
  assert.equal(w.gestures.length,1);assert.equal(w.gestures[0].gesture,true);
  for(const [main,page,start] of [[false,false,true],[true,true,true],[true,false,false]]){
    const secondary=create();await context.load(secondary,main,page,{codexflareStartup:start},'/',false);
    assert.equal(secondary.webContents.listenerCount('did-finish-load'),0);
  }
});
