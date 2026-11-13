#ifndef IRON_AVATAR_RENDERER_H
#define IRON_AVATAR_RENDERER_H
#include <new>
static ironasset::Mesh animatedKnight;
static u16* avatarIndices=NULL;
static float renderDt=0;
struct AvatarRenderer{
 S3DVertex* buffers[2];std::vector<ironasset::Vertex> current,target,frozen;
 int lastClip;float blend,lastWalk,lastHP;
 AvatarRenderer():lastClip(-1),blend(1),lastWalk(0),lastHP(100){buffers[0]=buffers[1]=NULL;}
 void init(){
  for(int b=0;b<2;b++){
   buffers[b]=(S3DVertex*)rsxMemalign(128,animatedKnight.vertices*sizeof(S3DVertex));
   if(!buffers[b]){stage("avatar allocation failed");exit(1);}
   for(unsigned i=0;i<animatedKnight.vertices;i++)new(&buffers[b][i])S3DVertex();
  }
 }
 void render(const iron::Fighter& f,bool hero){
  if(lastHP<=0&&f.hp>0){lastClip=-1;current.clear();}
  lastHP=f.hp;
  bool moving=f.walk>lastWalk+.00001f;lastWalk=f.walk;
  const char* name=f.hp<=0?"Death":(f.swing>=0?"Attack":(f.dodge>0?"Roll":(f.blocking?"Block":(moving?"Walk":"Idle"))));
  int id=animatedKnight.clip(name);const ironasset::Clip& c=animatedKnight.clips[id];
  float duration=(c.count-1)/c.fps;
  float time=game.clock;
  if(f.hp<=0)time=f.fall*duration;
  else if(f.swing>=0)time=iron::clamp(f.swing/.64f,0,1)*duration;
  else if(f.dodge>0)time=iron::clamp(1-f.dodge/.60f,0,1)*duration;
  else if(moving&&!f.blocking)time=f.walk/(2*iron::PI)*(c.count/c.fps);
  if(id!=lastClip){frozen=current;blend=frozen.empty()?1:0;lastClip=id;}
  blend=std::min(1.f,blend+renderDt/.12f);
  animatedKnight.sample(id,time,target);current=target;
  if(blend<1&&frozen.size()==target.size()){
   for(unsigned i=0;i<animatedKnight.vertices;i++){
    ironasset::Vertex& v=current[i];const ironasset::Vertex& a=frozen[i];
    v.x=a.x+(v.x-a.x)*blend;v.y=a.y+(v.y-a.y)*blend;v.z=a.z+(v.z-a.z)*blend;
    v.nx=a.nx+(v.nx-a.nx)*blend;v.ny=a.ny+(v.ny-a.ny)*blend;v.nz=a.nz+(v.nz-a.nz)*blend;
   }
  }
  S3DVertex* out=buffers[curr_fb];
  for(unsigned i=0;i<animatedKnight.vertices;i++){
   const ironasset::Vertex& v=current[i];out[i].pos=Vector3(v.x,v.y,v.z);out[i].nrm=Vector3(v.nx,v.ny,v.nz);out[i].u=v.u;out[i].v=v.v;
  }
  __sync_synchronize(); // Publish CPU writes before RSX consumes this buffer.
  Matrix4 root=Matrix4::translation(Vector3(f.pos.x,0,f.pos.z))*Matrix4::rotationY(f.yaw);
  SMeshBuffer mesh;mesh.vertices=out;mesh.cnt_vertices=animatedKnight.vertices;
  SMeshBuffer* saved=cube;cube=&mesh;
  for(size_t i=0;i<animatedKnight.groups.size();i++){
   const ironasset::Group& g=animatedKnight.groups[i];mesh.indices=avatarIndices+g.start;mesh.cnt_indices=g.count;
   float r=g.r,green=g.g,b=g.b;
   if(g.tint){float strength=std::max(r,std::max(green,b));r=r*.6f+strength*(hero?.14f:.68f)*.4f;green=green*.6f+strength*(hero?.33f:.12f)*.4f;b=b*.6f+strength*(hero?.65f:.1f)*.4f;}
   if(f.flash>0){r=1;green=.65f;b=.35f;}
   box(root,r,green,b);
  }
  cube=saved;
 }
};
static AvatarRenderer heroAvatar,enemyAvatar;
static void initAvatars(){
 std::string error;
 if(!animatedKnight.load("/dev_hdd0/game/P3IRON001/USRDIR/knight.iyam",error)){stage(error.c_str());exit(1);}
 avatarIndices=(u16*)rsxMemalign(128,animatedKnight.indices.size()*sizeof(u16));
 if(!avatarIndices){stage("avatar index allocation failed");exit(1);}
 memcpy(avatarIndices,animatedKnight.indices.data(),animatedKnight.indices.size()*sizeof(u16));
 heroAvatar.init();enemyAvatar.init();stage("animated knight ready");
}
#endif
