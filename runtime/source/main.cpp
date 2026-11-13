#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <malloc.h>
#include <ppu-types.h>
#include <lv2/systime.h>
#include <math.h>
#include "Forge.h"
#include "animated_mesh.h"

#include <sys/process.h>

#include <io/pad.h>
#include <rsx/rsx.h>
#include <sysutil/sysutil.h>

#include "acid.h"
#include "mesh.h"
#include "forge_atlas.h"
#include "forge_materials.h"
#include "rsxutil.h"

#include "diffuse_specular_shader_vpo.h"
#include "diffuse_specular_shader_fpo.h"

#define DEGTORAD(a)                     ( (a) *  0.01745329252f )
#define RADTODEG(a)                     ( (a) * 57.29577951f )

u32 running = 0;

u32 fp_offset;
u32 *fp_buffer;

u32 *texture_buffer;
u32 texture_offset;
static u32 *atlas_buffer=nullptr;
static u32 atlas_offset=0;
static u32 texture_width=128;
static bool atlasBound=false;
static int boundCustom=-1;
static std::vector<u32*> materialBuffers;
static std::vector<u32> materialOffsets;

// vertex shader
rsxProgramConst *projMatrix;
rsxProgramConst *mvMatrix;
rsxProgramConst *diffuseTint,*fogUniform;
static float fogSlope=0;

// fragment shader
rsxProgramAttrib *textureUnit;
rsxProgramConst *eyePosition;
rsxProgramConst *globalAmbient;
rsxProgramConst *litPosition;
rsxProgramConst *litColor;
rsxProgramConst *Kd;
rsxProgramConst *Ks;
rsxProgramConst *spec;

Point3 eye_pos = Point3(0.0f,0.0f,20.0f);
Point3 eye_dir = Point3(0.0f,0.0f,0.0f);
Vector3 up_vec = Vector3(0.0f,1.0f,0.0f);

void *vp_ucode = NULL;
rsxVertexProgram *vpo = (rsxVertexProgram*)diffuse_specular_shader_vpo;

void *fp_ucode = NULL;
rsxFragmentProgram *fpo = (rsxFragmentProgram*)diffuse_specular_shader_fpo;

static Matrix4 P;


static SMeshBuffer *cube = NULL;

SYS_PROCESS_PARAM(1001, 0x100000);

extern "C" {
static void program_exit_callback()
{
        gcmSetWaitFlip(context);
        rsxFinish(context,1);
}

static void sysutil_exit_callback(u64 status,u64 param,void *usrdata)
{
        switch(status) {
                case SYSUTIL_EXIT_GAME:
                        running = 0;
                        break;
                case SYSUTIL_DRAW_BEGIN:
                case SYSUTIL_DRAW_END:
                        break;
                default:
                        break;
        }
}
}
static void stage(const char* text);
static void init_texture()
{
        u32 i;
        u8 *buffer;


        texture_buffer = (u32*)rsxMemalign(128,(acid.width*acid.height*4));
        if(!texture_buffer) return;

        rsxAddressToOffset(texture_buffer,&texture_offset);

        buffer = (u8*)texture_buffer;
        for(i=0;i<acid.width*acid.height*4;i+=4) {
                buffer[i + 1] = 255;
                buffer[i + 2] = 255;
                buffer[i + 3] = 255;
                buffer[i + 0] = 255;
        }
        if(forge::useAtlas){
            atlas_buffer=(u32*)rsxMemalign(128,FORGE_ATLAS_SIZE*FORGE_ATLAS_SIZE*4);
            if(!atlas_buffer){stage("atlas allocation failed");return;}
            rsxAddressToOffset(atlas_buffer,&atlas_offset);
            for(unsigned i=0;i<FORGE_ATLAS_SIZE*FORGE_ATLAS_SIZE;i++){
                unsigned v=forgeAtlas565[i];
#ifdef FORGE_ATLAS_ARGB1555
                unsigned r=((v>>10)&31)*255/31,g=((v>>5)&31)*255/31,b=(v&31)*255/31,a=(v&0x8000)?0xff000000:0;
#else
                unsigned r=((v>>11)&31)*255/31,g=((v>>5)&63)*255/63,b=(v&31)*255/31,a=0xff000000;
#endif
                atlas_buffer[i]=a|(r<<16)|(g<<8)|b;
            }
            forge::metrics.gpuBytes+=FORGE_ATLAS_SIZE*FORGE_ATLAS_SIZE*4;
        }
        for(unsigned t=0;t<FORGE_MATERIAL_COUNT;t++){
            unsigned size=forgeMaterialImages[t].size;u32* pixels=(u32*)rsxMemalign(128,size*size*4);if(!pixels){stage("material texture allocation failed");exit(1);}u32 offset;rsxAddressToOffset(pixels,&offset);
            for(unsigned i=0;i<size*size;i++){unsigned v=forgeMaterialImages[t].pixels[i];pixels[i]=((v&0x8000)?0xff000000:0)|((((v>>10)&31)*255/31)<<16)|((((v>>5)&31)*255/31)<<8)|((v&31)*255/31);}
            materialBuffers.push_back(pixels);materialOffsets.push_back(offset);forge::metrics.gpuBytes+=size*size*4;
        }
}

static SMeshBuffer* createCube(f32 size)
{
        u32 i;
        SMeshBuffer *buffer = new SMeshBuffer();
        const u16 u[36] = {   0,1,2,   0,2,3,   1,4,5,   1,5,2,   4,7,6,         4,6,5, 
                                                  7,0,3,   7,3,6,   9,2,5,   9,5,8,   0,10,11,   0,7,10};

        buffer->cnt_indices = 36;
        buffer->indices = (u16*)rsxMemalign(128,buffer->cnt_indices*sizeof(u16));

        if(!buffer->indices) { fprintf(stderr,"index allocation failed\n"); exit(1); }
        for(i=0;i<36;i++) buffer->indices[i] = u[i];

        buffer->cnt_vertices = 12;
        buffer->vertices = (S3DVertex*)rsxMemalign(128,buffer->cnt_vertices*sizeof(S3DVertex));

        if(!buffer->vertices) { fprintf(stderr,"vertex allocation failed\n"); exit(1); }
        buffer->vertices[0] = S3DVertex(0,0,0, -1,-1,-1, 1, 0);
        buffer->vertices[1] = S3DVertex(1,0,0,  1,-1,-1, 1, 1);
        buffer->vertices[2] = S3DVertex(1,1,0,  1, 1,-1, 0, 1);
        buffer->vertices[3] = S3DVertex(0,1,0, -1, 1,-1, 0, 0);
        buffer->vertices[4] = S3DVertex(1,0,1,  1,-1, 1, 1, 0);
        buffer->vertices[5] = S3DVertex(1,1,1,  1, 1, 1, 0, 0);
        buffer->vertices[6] = S3DVertex(0,1,1, -1, 1, 1, 0, 1);
        buffer->vertices[7] = S3DVertex(0,0,1, -1,-1, 1, 1, 1);
        buffer->vertices[8] = S3DVertex(0,1,1, -1, 1, 1, 1, 0);
        buffer->vertices[9] = S3DVertex(0,1,0, -1, 1,-1, 1, 1);
        buffer->vertices[10] = S3DVertex(1,0,1,  1,-1, 1, 0, 1);
        buffer->vertices[11] = S3DVertex(1,0,0,  1,-1,-1, 0, 0);

        for(i=0;i<12;i++) {
                buffer->vertices[i].pos -= Vector3(0.5f,0.5f,0.5f);
                buffer->vertices[i].pos *= size;
        }

        return buffer;
}

static void setTexture(u8 textureUnit)
{
        u32 width = texture_width;
        u32 height = texture_width;
        u32 pitch = (width*4);
        gcmTexture texture;

        if(!texture_buffer) return;

        rsxInvalidateTextureCache(context,GCM_INVALIDATE_TEXTURE);

        texture.format          = (GCM_TEXTURE_FORMAT_A8R8G8B8 | GCM_TEXTURE_FORMAT_LIN);
        texture.mipmap          = 1;
        texture.dimension       = GCM_TEXTURE_DIMS_2D;
        texture.cubemap         = GCM_FALSE;
        texture.remap           = ((GCM_TEXTURE_REMAP_TYPE_REMAP << GCM_TEXTURE_REMAP_TYPE_B_SHIFT) |
                                                   (GCM_TEXTURE_REMAP_TYPE_REMAP << GCM_TEXTURE_REMAP_TYPE_G_SHIFT) |
                                                   (GCM_TEXTURE_REMAP_TYPE_REMAP << GCM_TEXTURE_REMAP_TYPE_R_SHIFT) |
                                                   (GCM_TEXTURE_REMAP_TYPE_REMAP << GCM_TEXTURE_REMAP_TYPE_A_SHIFT) |
                                                   (GCM_TEXTURE_REMAP_COLOR_B << GCM_TEXTURE_REMAP_COLOR_B_SHIFT) |
                                                   (GCM_TEXTURE_REMAP_COLOR_G << GCM_TEXTURE_REMAP_COLOR_G_SHIFT) |
                                                   (GCM_TEXTURE_REMAP_COLOR_R << GCM_TEXTURE_REMAP_COLOR_R_SHIFT) |
                                                   (GCM_TEXTURE_REMAP_COLOR_A << GCM_TEXTURE_REMAP_COLOR_A_SHIFT));
        texture.width           = width;
        texture.height          = height;
        texture.depth           = 1;
        texture.location        = GCM_LOCATION_RSX;
        texture.pitch           = pitch;
        texture.offset          = texture_offset;
        rsxLoadTexture(context,textureUnit,&texture);
        rsxTextureControl(context,textureUnit,GCM_TRUE,0<<8,12<<8,GCM_TEXTURE_MAX_ANISO_1);
        rsxTextureFilter(context,textureUnit,0,GCM_TEXTURE_LINEAR,GCM_TEXTURE_LINEAR,GCM_TEXTURE_CONVOLUTION_QUINCUNX);
        rsxTextureWrapMode(context,textureUnit,GCM_TEXTURE_CLAMP_TO_EDGE,GCM_TEXTURE_CLAMP_TO_EDGE,GCM_TEXTURE_CLAMP_TO_EDGE,0,GCM_TEXTURE_ZFUNC_LESS,0);
}

static void bindForgeTexture(bool atlas){
    if(boundCustom==-1&&atlasBound==atlas)return;
    boundCustom=-1;
    atlasBound=atlas;
    if(atlas&&atlas_buffer){u32* old=texture_buffer;u32 offset=texture_offset;texture_buffer=atlas_buffer;texture_offset=atlas_offset;texture_width=FORGE_ATLAS_SIZE;setTexture(textureUnit->index);texture_buffer=old;texture_offset=offset;texture_width=128;}
    else setTexture(textureUnit->index);
}
static void bindMaterialTexture(int id){
    if(id<0||id>=int(materialBuffers.size())){bindForgeTexture(false);return;}if(boundCustom==id)return;
    u32* old=texture_buffer;u32 offset=texture_offset;texture_buffer=materialBuffers[id];texture_offset=materialOffsets[id];texture_width=forgeMaterialImages[id].size;setTexture(textureUnit->index);texture_buffer=old;texture_offset=offset;texture_width=128;rsxTextureWrapMode(context,textureUnit->index,GCM_TEXTURE_REPEAT,GCM_TEXTURE_REPEAT,GCM_TEXTURE_CLAMP_TO_EDGE,0,GCM_TEXTURE_ZFUNC_LESS,0);atlasBound=false;boundCustom=id;
}

static void setDrawEnv()
{
        rsxSetColorMask(context,GCM_COLOR_MASK_B |
                                                        GCM_COLOR_MASK_G |
                                                        GCM_COLOR_MASK_R |
                                                        GCM_COLOR_MASK_A);

        rsxSetColorMaskMrt(context,0);

        u16 x,y,w,h;
        f32 min, max;
        f32 scale[4],offset[4];

        x = 0;
        y = 0;
        w = display_width;
        h = display_height;
        min = 0.0f;
        max = 1.0f;
        scale[0] = w*0.5f;
        scale[1] = h*-0.5f;
        scale[2] = (max - min)*0.5f;
        scale[3] = 0.0f;
        offset[0] = x + w*0.5f;
        offset[1] = y + h*0.5f;
        offset[2] = (max + min)*0.5f;
        offset[3] = 0.0f;

        rsxSetViewport(context,x, y, w, h, min, max, scale, offset);
        rsxSetScissor(context,x,y,w,h);

        rsxSetDepthTestEnable(context,GCM_TRUE);
        rsxSetDepthFunc(context,GCM_LESS);
        rsxSetShadeModel(context,GCM_SHADE_MODEL_SMOOTH);
        rsxSetDepthWriteEnable(context,1);
        rsxSetFrontFace(context,GCM_FRONTFACE_CCW);
}

void init_shader()
{
        u32 fpsize = 0;
        u32 vpsize = 0;

        rsxVertexProgramGetUCode(vpo, &vp_ucode, &vpsize);
        printf("vpsize: %d\n", vpsize);

        projMatrix = rsxVertexProgramGetConst(vpo,"projMatrix");
        mvMatrix = rsxVertexProgramGetConst(vpo,"modelViewMatrix");
        diffuseTint = rsxVertexProgramGetConst(vpo,"diffuseColor");
        fogUniform = rsxVertexProgramGetConst(vpo,"fogParams");

        rsxFragmentProgramGetUCode(fpo, &fp_ucode, &fpsize);
        printf("fpsize: %d\n", fpsize);

        fp_buffer = (u32*)rsxMemalign(64,fpsize);
        if(!fp_buffer) { fprintf(stderr,"fragment allocation failed\n"); exit(1); }
        memcpy(fp_buffer,fp_ucode,fpsize);
        rsxAddressToOffset(fp_buffer,&fp_offset);

        textureUnit = rsxFragmentProgramGetAttrib(fpo,"texture");
        eyePosition = rsxFragmentProgramGetConst(fpo,"eyePosition");
        globalAmbient = rsxFragmentProgramGetConst(fpo,"globalAmbient");
        litPosition = rsxFragmentProgramGetConst(fpo,"lightPosition");
        litColor = rsxFragmentProgramGetConst(fpo,"lightColor");
        spec = rsxFragmentProgramGetConst(fpo,"shininess");
        Ks = rsxFragmentProgramGetConst(fpo,"Ks");
        Kd = rsxFragmentProgramGetConst(fpo,"Kd");
}


static Matrix4 viewMatrix;
static FILE* logFile=nullptr;
static float frameMs=0,renderDt=0;
static void stage(const char* text){printf("%s\n",text);if(logFile){fprintf(logFile,"%s\n",text);fflush(logFile);}}
static float axis(unsigned value){float x=((float)value-128)/127;if(fabsf(x)<.20f)return 0;return copysignf((fabsf(x)-.20f)/.8f,x);}
static void box(const Matrix4& modelMatrix,float r,float g,float b)
{
    if(context->current+4096>context->end){stage("frame command budget exceeded");exit(1);}
    u32 offset;
    SMeshBuffer *mesh=cube;
    Point3 lightPos(5,18,8);
    float globalAmbientColor[3]={r*.4f,g*.4f,b*.4f};
    float lightColor[3]={0.85f,0.82f,0.75f};
    float materialColorDiffuse[3]={r,g,b};
    float materialColorSpecular[3]={0.1f,0.1f,0.1f};
    float shininess=12;
    Matrix4 modelMatrixIT,modelViewMatrix;
    Vector4 objEyePos,objLightPos;
        modelMatrixIT = inverse(modelMatrix);
        modelViewMatrix = transpose(viewMatrix*modelMatrix);

        objEyePos = modelMatrixIT*eye_pos;
        objLightPos = modelMatrixIT*lightPos;

        rsxAddressToOffset(&mesh->vertices[0].pos,&offset);
        rsxBindVertexArrayAttrib(context,GCM_VERTEX_ATTRIB_POS,0,offset,sizeof(S3DVertex),3,GCM_VERTEX_DATA_TYPE_F32,GCM_LOCATION_RSX);

        rsxAddressToOffset(&mesh->vertices[0].nrm,&offset);
        rsxBindVertexArrayAttrib(context,GCM_VERTEX_ATTRIB_NORMAL,0,offset,sizeof(S3DVertex),3,GCM_VERTEX_DATA_TYPE_F32,GCM_LOCATION_RSX);

        rsxAddressToOffset(&mesh->vertices[0].u,&offset);
        rsxBindVertexArrayAttrib(context,GCM_VERTEX_ATTRIB_TEX0,0,offset,sizeof(S3DVertex),2,GCM_VERTEX_DATA_TYPE_F32,GCM_LOCATION_RSX);

        rsxLoadVertexProgram(context,vpo,vp_ucode);
        rsxSetVertexProgramParameter(context,vpo,projMatrix,(float*)&P);
        rsxSetVertexProgramParameter(context,vpo,mvMatrix,(float*)&modelViewMatrix);

        float tint[4]={r,g,b,1};
        rsxSetVertexProgramParameter(context,vpo,diffuseTint,tint);
        float fog[4]={2.5f,fogSlope,0,0};
        rsxSetVertexProgramParameter(context,vpo,fogUniform,fog);

        rsxLoadFragmentProgramLocation(context,fpo,fp_offset,GCM_LOCATION_RSX);

        rsxSetUserClipPlaneControl(context,GCM_USER_CLIP_PLANE_DISABLE,
                                                                           GCM_USER_CLIP_PLANE_DISABLE,
                                                                           GCM_USER_CLIP_PLANE_DISABLE,
                                                                           GCM_USER_CLIP_PLANE_DISABLE,
                                                                           GCM_USER_CLIP_PLANE_DISABLE,
                                                                           GCM_USER_CLIP_PLANE_DISABLE);

        rsxAddressToOffset(&mesh->indices[0],&offset);
        rsxDrawIndexArray(context,GCM_TYPE_TRIANGLES,offset,mesh->cnt_indices,GCM_INDEX_TYPE_16B,GCM_LOCATION_RSX);
        forge::metrics.drawCalls++;forge::metrics.triangles+=mesh->cnt_indices/3;

}

#include "forge_models.h"
#include "world_renderer.h"
static void drawFrame(){
 if(forge::worldSettings.renderPolicy){
  if(auto player=forge::findId(forge::worldSettings.target))
   forge::worldSettings.renderPolicy(*player,forge::Input(),0);
 }
 worldRenderer.prepare();
 atlasBound=false;boundCustom=-1;forge::metrics.drawCalls=forge::metrics.triangles=0;setDrawEnv();setTexture(textureUnit->index);rsxSetClearColor(context,forge::background);rsxSetClearDepthStencil(context,0xffffff00);
 rsxClearSurface(context,GCM_CLEAR_R|GCM_CLEAR_G|GCM_CLEAR_B|GCM_CLEAR_A|GCM_CLEAR_S|GCM_CLEAR_Z);
 rsxSetZMinMaxControl(context,GCM_FALSE,GCM_TRUE,GCM_FALSE);for(u32 i=0;i<8;i++)rsxSetViewportClip(context,i,display_width,display_height);
 eye_pos=Point3(forge::cameraPosition.x,forge::cameraPosition.y,forge::cameraPosition.z);
 eye_dir=Point3(forge::cameraTarget.x,forge::cameraTarget.y,forge::cameraTarget.z);
 viewMatrix=Matrix4::lookAt(eye_pos,eye_dir,up_vec);
 for(int layer=0;layer<2;layer++){
  fogSlope=layer||!forge::worldSettings.renderPolicy?0.f:1.f/9.5f;
  P=transpose(Matrix4::perspective(DEGTORAD(layer?65:std::max(30.f,std::min(100.f,forge::cameraFov))),aspect_ratio,layer?.02f:.2f,layer?20.f:(forge::worldSettings.renderPolicy?forge::worldSettings.radius:1000.f)));
  if(layer){rsxSetClearDepthStencil(context,0xffffff00);rsxClearSurface(context,GCM_CLEAR_Z);viewMatrix=Matrix4::identity();eye_pos=Point3(0,0,0);}
  if(layer==0)worldRenderer.draw();
  for(size_t i=0;i<forge::entities.size();i++){
   const auto& e=forge::entities[i];if(e.scene!=forge::activeScene||!e.visible||e.viewModel!=(layer==1))continue;
   if(layer==0&&forge::entityRenderFilter&&!forge::entityRenderFilter(e))continue;
   if(forge::worldSettings.renderPolicy&&(e.renderRadius>0)&&!renderModels[i].initialized)
    renderModels[i].init(e.asset,e.meshCapacity,e.indexCapacity);
   Matrix4 m=Matrix4::translation(Vector3(e.position.x,e.position.y,e.position.z))*Matrix4::rotationX(DEGTORAD(e.rotation.x))*Matrix4::rotationY(DEGTORAD(e.rotation.y))*Matrix4::rotationZ(DEGTORAD(e.rotation.z))*Matrix4::scale(Vector3(e.scale.x,e.scale.y,e.scale.z));
   renderModels[i].draw(e,m,renderDt);
  }
 }
}
int main(int argc,const char* argv[]){
 forge::initialize();logFile=fopen((std::string(forge::rootPath)+"forge.log").c_str(),"w");stage("Forge main");
 void* host=memalign(HOST_ADDR_ALIGNMENT,HOSTBUFFER_SIZE);if(!host){stage("host allocation failed");return 1;}
 sysUtilRegisterCallback(0,sysutil_exit_callback,nullptr);init_screen(host,HOSTBUFFER_SIZE);stage("RSX ready");
 forge::cameraAspect=aspect_ratio;
 if(ioPadInit(7)!=0){stage("pad init failed");return 1;}init_shader();init_texture();
 if(!texture_buffer||(forge::useAtlas&&!atlas_buffer)){stage("texture allocation failed");return 1;}
 DebugFont::init();DebugFont::setScreenRes(display_width,display_height);if(!forge::hudText.empty())DebugFont::setSafeArea(0,0,0,0);cube=createCube(1);
 if(logFile)fprintf(logFile,"atlas=%p offset=%u first=%08x sampler=%u entities=%u\n",atlas_buffer,atlas_offset,atlas_buffer?atlas_buffer[0]:0,textureUnit->index,(unsigned)forge::entities.size());
 renderModels.resize(forge::entities.size());for(size_t i=0;i<forge::entities.size();i++){
  const auto& e=forge::entities[i];
  if(!forge::worldSettings.renderPolicy||!(e.renderRadius>0))
   renderModels[i].init(e.asset,e.meshCapacity,e.indexCapacity);
 }forge::sampleBones=sampleEntityBones;worldRenderer.init();forge::updateWorld=updateStreamedWorld;stage("scene assets ready");
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
    if(state.len>=8){connected=true;input.moveX=axis(state.ANA_L_H);input.moveY=-axis(state.ANA_L_V);input.lookX=axis(state.ANA_R_H);input.lookY=-axis(state.ANA_R_V);input.cross=state.BTN_CROSS&&!prevX;input.square=state.BTN_SQUARE&&!prevS;input.triangle=state.BTN_TRIANGLE&&!prevT;input.r1=state.BTN_R1&&!prevR;input.l1=state.BTN_L1;input.crossHeld=state.BTN_CROSS;bool builtInController=false;for(const auto& e:forge::entities)if(e.scene==forge::activeScene&&e.features.count("CharacterController"))builtInController=true;input.fireHeld=state.BTN_R2||(state.BTN_R1&&!builtInController);input.aimHeld=state.BTN_L2||(state.BTN_L1&&!builtInController);input.sprint=state.BTN_L3;prevX=state.BTN_CROSS;prevS=state.BTN_SQUARE;prevT=state.BTN_TRIANGLE;prevR=state.BTN_R1;}
   }
  }else{port=-1;memset(&state,0,sizeof(state));}
  if(connected){
   queued.cross=queued.cross||input.cross;queued.square=queued.square||input.square;queued.triangle=queued.triangle||input.triangle;queued.r1=queued.r1||input.r1;
   input.cross=queued.cross;input.square=queued.square;input.triangle=queued.triangle;input.r1=queued.r1;accumulator+=dt;
   while(accumulator>=1.f/60){forge::step(input,1.f/60);input.cross=input.square=input.triangle=input.r1=false;queued=forge::Input();accumulator-=1.f/60;}
  }else{accumulator=0;queued=forge::Input();}
  renderDt=connected?dt:0;u64 submitStart=sysGetSystemTime();drawFrame();forge::metrics.submitMs=(sysGetSystemTime()-submitStart)*.001f;DebugFont::setScreenRes(forge::hudText.empty()?display_width:display_width/2,forge::hudText.empty()?display_height:display_height/2);DebugFont::setSafeArea(12,12,12,12);DebugFont::setPosition(0,0);DebugFont::setColor(1,1,1,1);
  char text[256];snprintf(text,sizeof(text),"PS3 FORGE | %s | %.1f ms/frame\n%s | START: Exit",forge::sceneNames[forge::activeScene].c_str(),frameMs,connected?"Controller ready":"Connect controller - paused");DebugFont::print(forge::hudText.empty()?text:forge::hudText.c_str());
  if(forge::crosshair){DebugFont::setSafeArea(0,0,0,0);DebugFont::setPosition(display_width/4-4,display_height/4-4);DebugFont::print("+");}
  if(forge::showProfiler){char profile[384];snprintf(profile,sizeof(profile),"\nCPU logic %.2f ms  submit %.2f ms  flip wait %.2f ms\n%u draws  %u triangles  assets %.2f MiB  GPU allocations %.2f MiB",forge::metrics.logicMs,forge::metrics.submitMs,forge::metrics.flipMs,forge::metrics.drawCalls,forge::metrics.triangles,forge::metrics.assetBytes/1048576.,forge::metrics.gpuBytes/1048576.);DebugFont::print(profile);for(const auto& e:forge::entities)if(e.scene==forge::activeScene&&!e.debugState.empty()){DebugFont::print(("\n"+e.name+": "+e.debugState).c_str());}}
  if(!forge::worldStatus.empty()&&forge::showProfiler)DebugFont::print(("\n"+forge::worldStatus).c_str());
  if(!forge::lastError.empty())DebugFont::print(("\nERROR: "+forge::lastError).c_str());
  if(!connected&&!forge::hudText.empty()){DebugFont::setPosition(12,display_height/2-24);DebugFont::print("Connect a controller to play");}u64 flipStart=sysGetSystemTime();flip();forge::metrics.flipMs=(sysGetSystemTime()-flipStart)*.001f;
  if(first){stage("first frame submitted");first=false;}frames++;if(now-stats>=1000000){frameMs=(now-stats)*.001f/frames;frames=0;stats=now;}
 }
 stage("exit requested");program_exit_callback();DebugFont::shutdown();ioPadEnd();if(logFile)fclose(logFile);return 0;
}
