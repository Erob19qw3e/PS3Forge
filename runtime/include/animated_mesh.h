#ifndef IRON_ANIMATED_MESH_H
#define IRON_ANIMATED_MESH_H
#include <vector>
#include <algorithm>
#include <utility>
#include <string>
#include <fstream>
#include <cstring>
#include <cmath>
#include <stdexcept>
#include <stdint.h>
#include <array>
#include <set>
#include "forge_math.h"
namespace ironasset {
struct Vertex{float x,y,z,nx,ny,nz,u,v;};
static_assert(sizeof(Vertex)==32,"Vertex layout");
struct Group{uint32_t start,count;float r,g,b;uint32_t tint;};
struct Clip{std::string name;uint32_t first,count;float fps;bool loop;};
struct Bone{std::string name;int parent;forgemath::Matrix inverseBind;};
struct SkinVertex{Vertex vertex;uint16_t joints[4];float weights[4];};
struct AnimationEvent{uint32_t clip;float time;std::string name;};
struct Reader{
 const std::vector<unsigned char>& b;size_t p;
 Reader(const std::vector<unsigned char>& v):b(v),p(0){}
 void need(size_t n){if(n>b.size()-p)throw std::runtime_error("truncated asset");}
 uint32_t u32(){need(4);uint32_t v=(uint32_t(b[p])<<24)|(uint32_t(b[p+1])<<16)|(uint32_t(b[p+2])<<8)|b[p+3];p+=4;return v;}
 uint16_t u16(){need(2);uint16_t v=(uint16_t(b[p])<<8)|b[p+1];p+=2;return v;}
 float f32(){uint32_t v=u32();float f;std::memcpy(&f,&v,4);if(!std::isfinite(f))throw std::runtime_error("non-finite asset float");return f;}
 std::string name(){need(32);const char* s=reinterpret_cast<const char*>(&b[p]);const void* end=std::memchr(s,0,32);if(!end)throw std::runtime_error("clip name");std::string v(s);p+=32;return v;}
};
struct Mesh{
 uint32_t vertices,frames;std::vector<Group> groups;std::vector<Clip> clips;std::vector<uint16_t> indices;std::vector<Vertex> poses;
 std::vector<Bone> bones;std::vector<SkinVertex> skin;std::vector<std::array<float,10> > keys;std::vector<AnimationEvent> events;
 Mesh():vertices(0),frames(0){}
 bool parseSkeletal(const std::vector<unsigned char>& bytes,std::string& error){
  try{
   Reader r(bytes);if(r.u32()!=0x4959414d||r.u32()!=2)throw std::runtime_error("skeletal magic");
   uint32_t nv=r.u32(),ni=r.u32(),ng=r.u32(),nc=r.u32(),nf=r.u32(),stride=r.u32(),nb=r.u32(),ne=r.u32(),flags=r.u32(),reserved=r.u32();
   if(!nv||nv>20000||!ni||ni>1000000||ni%3||!ng||ng>64||!nc||nc>128||!nf||nf>4096||!nb||nb>128||ne>1024||stride!=56||flags||reserved)throw std::runtime_error("skeletal counts");
   uint64_t expected=48+uint64_t(ng)*24+uint64_t(nc)*48+uint64_t(nb)*100+uint64_t(ne)*40+uint64_t(ni)*2+uint64_t(nv)*56+uint64_t(nf)*nb*40;
   if(expected!=bytes.size()||expected>64*1024*1024)throw std::runtime_error("skeletal size/budget");
   Mesh m;m.vertices=nv;m.frames=nf;m.groups.reserve(ng);m.clips.reserve(nc);m.bones.reserve(nb);m.events.reserve(ne);m.indices.reserve(ni);m.skin.reserve(nv);m.keys.reserve(size_t(nf)*nb);
   for(uint32_t i=0;i<ng;i++){Group g;g.start=r.u32();g.count=r.u32();g.r=r.f32();g.g=r.f32();g.b=r.f32();g.tint=r.u32();if(g.start>ni||g.count>ni-g.start||g.count%3||g.tint>1||g.r<0||g.r>1||g.g<0||g.g>1||g.b<0||g.b>1)throw std::runtime_error("skeletal group");m.groups.push_back(g);}
   std::set<std::string> names;
   for(uint32_t i=0;i<nc;i++){Clip c;c.name=r.name();c.first=r.u32();c.count=r.u32();c.fps=r.f32();uint32_t loop=r.u32();c.loop=loop!=0;if(c.name.empty()||!names.insert(c.name).second||!c.count||c.first>=nf||c.count>nf-c.first||c.fps<=0||c.fps>120||loop>1)throw std::runtime_error("skeletal clip");m.clips.push_back(c);}
   names.clear();
   for(uint32_t i=0;i<nb;i++){Bone b;b.name=r.name();b.parent=int32_t(r.u32());if(b.name.empty()||!names.insert(b.name).second||b.parent< -1||b.parent>=int(i))throw std::runtime_error("bone hierarchy");for(float& x:b.inverseBind.v){x=r.f32();if(fabsf(x)>100000)throw std::runtime_error("inverse bind bounds");}m.bones.push_back(b);}
   for(uint32_t i=0;i<ne;i++){AnimationEvent e;e.clip=r.u32();e.time=r.f32();e.name=r.name();if(e.clip>=nc||e.time<0||e.time>m.clips[e.clip].count/m.clips[e.clip].fps||e.name.empty())throw std::runtime_error("skeletal event");m.events.push_back(e);}
   for(uint32_t i=0;i<ni;i++){uint16_t n=r.u16();if(n>=nv)throw std::runtime_error("skeletal index");m.indices.push_back(n);}
   for(uint32_t i=0;i<nv;i++){SkinVertex s;s.vertex.x=r.f32();s.vertex.y=r.f32();s.vertex.z=r.f32();s.vertex.nx=r.f32();s.vertex.ny=r.f32();s.vertex.nz=r.f32();s.vertex.u=r.f32();s.vertex.v=r.f32();if(fabsf(s.vertex.x)>100||fabsf(s.vertex.y)>100||fabsf(s.vertex.z)>100||fabsf(s.vertex.nx)>2||fabsf(s.vertex.ny)>2||fabsf(s.vertex.nz)>2)throw std::runtime_error("skeletal vertex bounds");for(auto& j:s.joints){j=r.u16();if(j>=nb)throw std::runtime_error("skeletal joint");}float total=0;for(float& w:s.weights){w=r.f32();if(w<0||w>1)throw std::runtime_error("skeletal weight");total+=w;}if(fabsf(total-1)>.001f)throw std::runtime_error("skeletal weight sum");m.skin.push_back(s);}
   for(uint32_t f=0;f<nf;f++)for(uint32_t b=0;b<nb;b++){std::array<float,10> k;for(float& x:k)x=r.f32();float q=0;for(int j=0;j<3;j++)if(fabsf(k[j])>1000)throw std::runtime_error("bone translation");for(int j=3;j<7;j++)q+=k[j]*k[j];if(fabsf(q-1)>.003f)throw std::runtime_error("bone quaternion");for(int j=7;j<10;j++)if(k[j]<.0001f||k[j]>100)throw std::runtime_error("bone scale");m.keys.push_back(k);}
   *this=std::move(m);return true;
  }catch(const std::exception& e){error=e.what();return false;}
 }
 bool parse(const std::vector<unsigned char>& bytes,std::string& error){
  try{
   Reader r(bytes);uint32_t magic=r.u32(),version=r.u32();if(magic==0x4959414d&&version==2)return parseSkeletal(bytes,error);if(magic!=0x4959414d||version!=1)throw std::runtime_error("asset magic/version");
   uint32_t nv=r.u32(),ni=r.u32(),ng=r.u32(),nc=r.u32(),nf=r.u32(),stride=r.u32();
   if(nv==0||nv>20000||ni==0||ni>1000000||ni%3||ng==0||ng>64||nc==0||nc>128||nf==0||nf>4096||stride!=32)throw std::runtime_error("asset counts");
   uint64_t data=uint64_t(nv)*nf*32,expected=32+uint64_t(ng)*24+uint64_t(nc)*48+uint64_t(ni)*2+data;
   if(data>64*1024*1024||expected!=bytes.size())throw std::runtime_error("asset size/budget");
   Mesh m;m.vertices=nv;m.frames=nf;
   for(uint32_t i=0;i<ng;i++){Group g;g.start=r.u32();g.count=r.u32();g.r=r.f32();g.g=r.f32();g.b=r.f32();g.tint=r.u32();if(g.start>ni||g.count>ni-g.start||g.count%3||g.tint>1||g.r<0||g.r>1||g.g<0||g.g>1||g.b<0||g.b>1)throw std::runtime_error("asset group");m.groups.push_back(g);}
   for(uint32_t i=0;i<nc;i++){Clip c;c.name=r.name();c.first=r.u32();c.count=r.u32();c.fps=r.f32();c.loop=r.u32()!=0;if(c.count==0||c.first>=nf||c.count>nf-c.first||c.fps<=0||c.fps>120)throw std::runtime_error("asset clip");m.clips.push_back(c);}
   m.indices.resize(ni);for(uint32_t i=0;i<ni;i++){m.indices[i]=r.u16();if(m.indices[i]>=nv)throw std::runtime_error("asset index");}
   m.poses.resize(size_t(nv)*nf);
   for(size_t i=0;i<m.poses.size();i++){Vertex& v=m.poses[i];v.x=r.f32();v.y=r.f32();v.z=r.f32();v.nx=r.f32();v.ny=r.f32();v.nz=r.f32();v.u=r.f32();v.v=r.f32();if(std::fabs(v.x)>100||std::fabs(v.y)>100||std::fabs(v.z)>100||std::fabs(v.nx)>2||std::fabs(v.ny)>2||std::fabs(v.nz)>2)throw std::runtime_error("asset vertex bounds");}
   *this=std::move(m);return true;
  }catch(const std::exception& e){error=e.what();return false;}
 }
 bool load(const char* path,std::string& error){
  std::ifstream f(path,std::ios::binary|std::ios::ate);if(!f){error="cannot open animated mesh";return false;}std::streamoff n=f.tellg();if(n<32||n>70*1024*1024){error="animated mesh file size";return false;}
  std::vector<unsigned char> b(static_cast<size_t>(n));f.seekg(0);if(!f.read(reinterpret_cast<char*>(b.data()),n)){error="animated mesh read";return false;}return parse(b,error);
 }
 int clip(const char* name)const{for(size_t i=0;i<clips.size();i++)if(clips[i].name==name)return int(i);return 0;}
 void boneKey(int id,float seconds,size_t i,float* v)const{
  const Clip& c=clips.at(id);float frame=std::max(0.f,seconds*c.fps);frame=c.loop?fmodf(frame,float(c.count)):std::min(frame,float(c.count-1));uint32_t a=uint32_t(frame),b=c.loop?(a+1)%c.count:std::min(a+1,c.count-1);float t=frame-a;
  const auto& x=keys[(c.first+a)*bones.size()+i];const auto& y=keys[(c.first+b)*bones.size()+i];for(int j=0;j<10;j++)v[j]=x[j]+(y[j]-x[j])*t;
  float dot=0;for(int j=3;j<7;j++)dot+=x[j]*y[j];float length=0;for(int j=3;j<7;j++){v[j]=x[j]+((dot<0?-y[j]:y[j])-x[j])*t;length+=v[j]*v[j];}length=sqrtf(std::max(1e-12f,length));for(int j=3;j<7;j++)v[j]/=length;
 }
 void boneMatrices(int id,float seconds,std::vector<forgemath::Matrix>& out,int previous=-1,float previousTime=0,float alpha=1)const{
  out.clear();if(bones.empty())return;
  for(size_t i=0;i<bones.size();i++){
   float v[10];boneKey(id,seconds,i,v);
   if(previous>=0&&alpha<1){float a[10],dot=0,length=0;boneKey(previous,previousTime,i,a);for(int j=3;j<7;j++)dot+=v[j]*a[j];for(int j=0;j<10;j++){float target=(j>=3&&j<7&&dot<0)?-v[j]:v[j];v[j]=a[j]+(target-a[j])*alpha;if(j>=3&&j<7)length+=v[j]*v[j];}length=sqrtf(std::max(1e-12f,length));for(int j=3;j<7;j++)v[j]/=length;}
   forgemath::Matrix m=forgemath::trs(v,v+3,v+7);if(bones[i].parent>=0)m=out[bones[i].parent]*m;out.push_back(m);
  }
 }
 void skinPose(const std::vector<forgemath::Matrix>& globals,std::vector<Vertex>& out)const{
   std::vector<forgemath::Matrix> world=globals,normal(world.size());
   // Inverse-transpose once per bone, rather than once per vertex influence.
   for(size_t i=0;i<world.size();i++){world[i]=world[i]*bones[i].inverseBind;for(int j=0;j<3;j++){float n[3];world[i].normal(j==0,j==1,j==2,n);for(int k=0;k<3;k++)normal[i].v[k*4+j]=n[k];}}
   out.resize(vertices);
   for(size_t i=0;i<skin.size();i++){const auto& s=skin[i];Vertex v=s.vertex;v.x=v.y=v.z=v.nx=v.ny=v.nz=0;for(int j=0;j<4;j++)if(s.weights[j]>0){float p[3],n[3];world[s.joints[j]].point(s.vertex.x,s.vertex.y,s.vertex.z,p);normal[s.joints[j]].point(s.vertex.nx,s.vertex.ny,s.vertex.nz,n);v.x+=p[0]*s.weights[j];v.y+=p[1]*s.weights[j];v.z+=p[2]*s.weights[j];v.nx+=n[0]*s.weights[j];v.ny+=n[1]*s.weights[j];v.nz+=n[2]*s.weights[j];}float l=sqrtf(v.nx*v.nx+v.ny*v.ny+v.nz*v.nz);if(l>1e-8f){v.nx/=l;v.ny/=l;v.nz/=l;}out[i]=v;}
 }
 void sample(int id,float seconds,std::vector<Vertex>& out)const{
  if(!bones.empty()){
   std::vector<forgemath::Matrix> world;boneMatrices(id,seconds,world);skinPose(world,out);return;
  }
  const Clip& c=clips.at(id);float frame=std::max(0.f,seconds*c.fps);
  if(c.loop)frame=std::fmod(frame,float(c.count));else frame=std::min(frame,float(c.count-1));
  uint32_t a=uint32_t(frame),b=c.loop?(a+1)%c.count:std::min(a+1,c.count-1);float t=frame-a;
  const Vertex* x=&poses[size_t(c.first+a)*vertices];const Vertex* y=&poses[size_t(c.first+b)*vertices];out.resize(vertices);
  for(uint32_t i=0;i<vertices;i++){
   out[i].x=x[i].x+(y[i].x-x[i].x)*t;out[i].y=x[i].y+(y[i].y-x[i].y)*t;out[i].z=x[i].z+(y[i].z-x[i].z)*t;
   out[i].nx=x[i].nx+(y[i].nx-x[i].nx)*t;out[i].ny=x[i].ny+(y[i].ny-x[i].ny)*t;out[i].nz=x[i].nz+(y[i].nz-x[i].nz)*t;out[i].u=x[i].u;out[i].v=x[i].v;
  }
 }
};
}
#endif
