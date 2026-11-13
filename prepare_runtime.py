from pathlib import Path
root=Path(__file__).parent/'runtime'
p=root/'source/main.cpp';s=p.read_text()
prefix=s[:s.index('static float yaw=')].replace('#include "combat.h"','#include "Forge.h"')
box=s[s.index('static void box('):s.index('static void block(')]
body=r'''
static Matrix4 viewMatrix;
static FILE* logFile=nullptr;
static float frameMs=0,renderDt=0;
static void stage(const char* text){printf("%s\n",text);if(logFile){fprintf(logFile,"%s\n",text);fflush(logFile);}}
static float axis(unsigned value){float x=((float)value-128)/127;if(fabsf(x)<.20f)return 0;return copysignf((fabsf(x)-.20f)/.8f,x);}
'''+box+r'''
#include "forge_models.h"
static void drawFrame(){
 setDrawEnv();setTexture(textureUnit->index);rsxSetClearColor(context,forge::background);rsxSetClearDepthStencil(context,0xffffff00);
 rsxClearSurface(context,GCM_CLEAR_R|GCM_CLEAR_G|GCM_CLEAR_B|GCM_CLEAR_A|GCM_CLEAR_S|GCM_CLEAR_Z);
 rsxSetZMinMaxControl(context,GCM_FALSE,GCM_TRUE,GCM_FALSE);for(u32 i=0;i<8;i++)rsxSetViewportClip(context,i,display_width,display_height);
 eye_pos=Point3(forge::cameraPosition.x,forge::cameraPosition.y,forge::cameraPosition.z);
 eye_dir=Point3(forge::cameraTarget.x,forge::cameraTarget.y,forge::cameraTarget.z);
 viewMatrix=Matrix4::lookAt(eye_pos,eye_dir,up_vec);
 for(size_t i=0;i<forge::entities.size();i++){
  const auto& e=forge::entities[i];if(e.scene!=forge::activeScene)continue;
  Matrix4 m=Matrix4::translation(Vector3(e.position.x,e.position.y,e.position.z))*Matrix4::rotationX(DEGTORAD(e.rotation.x))*Matrix4::rotationY(DEGTORAD(e.rotation.y))*Matrix4::rotationZ(DEGTORAD(e.rotation.z))*Matrix4::scale(Vector3(e.scale.x,e.scale.y,e.scale.z));
  renderModels[i].draw(e,m,renderDt);
 }
}
int main(int argc,const char* argv[]){
 forge::initialize();logFile=fopen((std::string(forge::rootPath)+"forge.log").c_str(),"w");stage("Forge main");
 void* host=memalign(HOST_ADDR_ALIGNMENT,HOSTBUFFER_SIZE);if(!host){stage("host allocation failed");return 1;}
 sysUtilRegisterCallback(0,sysutil_exit_callback,nullptr);init_screen(host,HOSTBUFFER_SIZE);stage("RSX ready");
 if(ioPadInit(7)!=0){stage("pad init failed");return 1;}init_shader();init_texture();
 if(!texture_buffer){stage("texture allocation failed");return 1;}
 DebugFont::init();DebugFont::setScreenRes(display_width,display_height);cube=createCube(1);
 renderModels.resize(forge::entities.size());for(size_t i=0;i<forge::entities.size();i++)renderModels[i].init(forge::entities[i].asset);stage("scene assets ready");
 P=transpose(Matrix4::perspective(DEGTORAD(65),aspect_ratio,.2f,1000));setDrawEnv();setRenderTarget(curr_fb);
 padData state={};int port=-1;bool prevX=false,prevS=false,prevT=false,prevR=false;forge::Input queued;
 u64 last=sysGetSystemTime(),stats=last;unsigned frames=0;float accumulator=0;bool first=true;running=1;
 while(running){
  u64 now=sysGetSystemTime();float dt=std::min(.05f,(now-last)*.000001f);last=now;sysUtilCheckCallback();if(!running)break;
  bool connected=false;forge::Input input;padInfo2 info={};
  if(ioPadGetInfo2(&info)==0){
   if(port<0||!(info.port_status[port]&1)){port=-1;memset(&state,0,sizeof(state));prevX=prevS=prevT=prevR=false;for(int i=0;i<MAX_PORT_NUM;i++)if(info.port_status[i]&1){port=i;break;}}
   if(port>=0){padData next={};if(ioPadGetData(port,&next)==0&&next.len>0){state.BTN_START=next.BTN_START;if(next.len>=8)state=next;}
    if(state.BTN_START)break;
    if(state.len>=8){connected=true;input.moveX=axis(state.ANA_L_H);input.moveY=-axis(state.ANA_L_V);input.lookX=axis(state.ANA_R_H);input.lookY=-axis(state.ANA_R_V);input.cross=state.BTN_CROSS&&!prevX;input.square=state.BTN_SQUARE&&!prevS;input.triangle=state.BTN_TRIANGLE&&!prevT;input.r1=state.BTN_R1&&!prevR;input.l1=state.BTN_L1;input.crossHeld=state.BTN_CROSS;prevX=state.BTN_CROSS;prevS=state.BTN_SQUARE;prevT=state.BTN_TRIANGLE;prevR=state.BTN_R1;}
   }
  }else{port=-1;memset(&state,0,sizeof(state));}
  if(connected){
   queued.cross=queued.cross||input.cross;queued.square=queued.square||input.square;queued.triangle=queued.triangle||input.triangle;queued.r1=queued.r1||input.r1;
   input.cross=queued.cross;input.square=queued.square;input.triangle=queued.triangle;input.r1=queued.r1;accumulator+=dt;
   while(accumulator>=1.f/60){forge::step(input,1.f/60);input.cross=input.square=input.triangle=input.r1=false;queued=forge::Input();accumulator-=1.f/60;}
  }else{accumulator=0;queued=forge::Input();}
  renderDt=connected?dt:0;drawFrame();DebugFont::setPosition(16,16);DebugFont::setColor(1,1,1,1);
  char text[256];snprintf(text,sizeof(text),"PS3 FORGE | %s | %.1f ms/frame\n%s | START: Exit",forge::sceneNames[forge::activeScene].c_str(),frameMs,connected?"Controller ready":"Connect controller - paused");DebugFont::print(text);flip();
  if(first){stage("first frame submitted");first=false;}frames++;if(now-stats>=1000000){frameMs=(now-stats)*.001f/frames;frames=0;stats=now;}
 }
 stage("exit requested");program_exit_callback();DebugFont::shutdown();ioPadEnd();if(logFile)fclose(logFile);return 0;
}
'''
p.write_text(prefix+body)
p=root/'Makefile';s=p.read_text().replace('SOURCES\t\t:=\tsource support/', 'SOURCES\t\t:=\tsource source/scripts support/')
if 'source/scripts' not in s:
    import re
    s=re.sub(r'^(SOURCES\s*:=\s*)source ',r'\1source source/scripts ',s,flags=re.M)
s=s.replace('Iron Yard 0.2','PS3 Forge Demo').replace('P3IRON001','P3FGDEMO1');p.write_text(s)
print('Native runtime prepared')
