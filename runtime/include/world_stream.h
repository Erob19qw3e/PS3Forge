#ifndef FORGE_WORLD_STREAM_H
#define FORGE_WORLD_STREAM_H
#include <vector>
#include <map>
#include <set>
#include <string>
#include <fstream>
#include <stdint.h>
#include <cstring>
#include <cmath>
#include <algorithm>
#include <stdexcept>
#include "animated_mesh.h"
#include "world_collision.h"
namespace forgeworld {
struct Bounds{float lo[3],hi[3];float distance2(float x,float z)const{float dx=std::max(lo[0]-x,std::max(0.f,x-hi[0])),dz=std::max(lo[2]-z,std::max(0.f,z-hi[2]));return dx*dx+dz*dz;}};
struct Texture{uint32_t offset,size;};
struct Model{uint32_t offset,bytes,vertices,indices,groups,finer;};
struct Instance{uint32_t model,flags,source,layers;float transform[12];Bounds bounds;};
struct Cell{uint32_t first,count;};
struct Selection{std::vector<uint32_t> instances,modelForInstance;std::map<uint32_t,uint32_t> byInstance;std::set<uint32_t> models;unsigned detailed=0,medium=0,coarse=0;unsigned vertices=0,draws=0;size_t bytes=0;};
struct World{
 std::map<unsigned,std::vector<Triangle> > collisionModels;std::vector<std::array<uint32_t,3> > textureSets;std::map<unsigned,Bounds> modelBounds;std::set<unsigned> dynamicInstances,hiddenInstances;
 std::string path;std::vector<Texture> textures;std::vector<Model> models;std::vector<Instance> instances;std::map<std::pair<int,int>,Cell> cells;std::vector<uint32_t> refs,marks;uint32_t generation=0;float cellSize=64,lodNear=20,lodMid=60;unsigned version=1;size_t metadataBytes=0;
 static std::vector<unsigned char> read(std::ifstream& f,size_t offset,size_t bytes){f.clear();f.seekg(offset);std::vector<unsigned char> b(bytes);if(!f.read(reinterpret_cast<char*>(b.data()),bytes))throw std::runtime_error("world read");return b;}
 bool open(const std::string& filename,std::string& error){
  try{
   std::ifstream f(filename.c_str(),std::ios::binary|std::ios::ate);auto length=f.tellg();if(length<64||length>80*1024*1024)throw std::runtime_error("world size");auto header=read(f,0,64);ironasset::Reader h(header);if(h.u32()!=0x46575331)throw std::runtime_error("world magic");unsigned format=h.u32();if(format!=1&&format!=2&&format!=3&&format!=4)throw std::runtime_error("world version");uint32_t nm=h.u32(),ni=h.u32(),nc=h.u32(),nr=h.u32(),mo=h.u32(),io=h.u32(),co=h.u32(),ro=h.u32(),data=h.u32(),total=h.u32();float cell=h.f32(),near=20,mid=60;uint32_t textureStart=uint32_t(length);bool badExtra=false;if(format>=2){near=h.f32();mid=h.f32();uint32_t extra=h.u32();if(format>=3)textureStart=extra;badExtra=(format==2&&extra)||textureStart>uint32_t(length)||textureStart<data||near<1||near>=mid||mid>500;}else{badExtra=h.u32()||h.u32()||h.u32();}if(badExtra||!nm||nm>4096||!ni||ni>100000||!nc||nc>20000||nr>2000000||cell<16||cell>256||mo!=64||io!=64+nm*24||co!=io+ni*88||ro!=co+nc*16||data!=ro+nr*4||total!=uint32_t(length))throw std::runtime_error("world tables");
   auto bytes=read(f,64,data-64);ironasset::Reader r(bytes);World w;w.path=filename;w.cellSize=cell;w.lodNear=near;w.lodMid=mid;w.version=format;w.models.reserve(nm);w.instances.reserve(ni);w.refs.reserve(nr);uint32_t cursor=data;
   for(uint32_t i=0;i<nm;i++){Model m;m.offset=r.u32();m.bytes=r.u32();m.vertices=r.u32();m.indices=r.u32();m.groups=r.u32();m.finer=r.u32();if((format==1&&m.finer)||m.finer>nm||m.offset!=cursor||!m.vertices||m.vertices>20000||!m.indices||m.indices>1000000||m.indices%3||!m.groups||m.groups>64||m.bytes!=m.groups*24+m.indices*2+m.vertices*32||uint64_t(m.offset)+m.bytes>total)throw std::runtime_error("world model table");cursor+=m.bytes;w.models.push_back(m);}if(cursor!=textureStart)throw std::runtime_error("world trailing bytes");for(unsigned i=0;i<nm;i++){std::set<unsigned> seen;unsigned at=i;while(true){if(!seen.insert(at).second||seen.size()>8)throw std::runtime_error("world LOD cycle");if(!w.models[at].finer)break;at=w.models[at].finer-1;}}
   for(uint32_t i=0;i<ni;i++){Instance v;v.model=r.u32();v.flags=r.u32();v.source=r.u32();v.layers=r.u32();if((format<4&&v.layers)||v.model>=nm||v.flags>3||v.source!=i)throw std::runtime_error("world instance table");for(float& x:v.transform){x=r.f32();if(fabsf(x)>1e7f)throw std::runtime_error("world transform");}for(float& x:v.bounds.lo)x=r.f32();for(float& x:v.bounds.hi)x=r.f32();for(int k=0;k<3;k++)if(v.bounds.lo[k]>v.bounds.hi[k])throw std::runtime_error("world bounds");w.instances.push_back(v);}
   for(uint32_t i=0;i<nc;i++){int x=int32_t(r.u32()),z=int32_t(r.u32());Cell c;c.first=r.u32();c.count=r.u32();if(uint64_t(c.first)+c.count>nr||!w.cells.emplace(std::make_pair(x,z),c).second)throw std::runtime_error("world cells");}
   for(uint32_t i=0;i<nr;i++){uint32_t v=r.u32();if(v>=ni||!(w.instances[v].flags&1))throw std::runtime_error("world reference");w.refs.push_back(v);}if(format>=3){auto th=read(f,textureStart,16);ironasset::Reader tr(th);if(tr.u32()!=0x46575431||tr.u32()!=(format==4?2:1))throw std::runtime_error("world texture magic");unsigned count=tr.u32();if(!count||count>(format==4?1024u:64u)||tr.u32()!=total-textureStart)throw std::runtime_error("world texture header");uint32_t at=textureStart+16,gpu=0;for(unsigned i=0;i<count;i++){auto tb=read(f,at,8);ironasset::Reader rr(tb);unsigned width=rr.u32(),size=rr.u32();at+=8;if((width!=64&&width!=128&&width!=256)||size!=width*width*4||uint64_t(at)+size>total)throw std::runtime_error("world texture record");w.textures.push_back({at,width});at+=size;gpu+=size;}if(format==4){auto extra=read(f,at,total-at);ironasset::Reader er(extra);unsigned sets=er.u32();if(sets>1024)throw std::runtime_error("world texture sets");for(unsigned j=0;j<sets;j++){std::array<uint32_t,3>s;for(auto&t:s){t=er.u32();if(t>count)throw std::runtime_error("world texture set index");}w.textureSets.push_back(s);}unsigned cm=er.u32(),triangles=0;if(cm>nm)throw std::runtime_error("world collision count");for(unsigned j=0;j<cm;j++){unsigned model=er.u32(),n=er.u32();triangles+=n;if(model>=nm||w.collisionModels.count(model)||n>200000||triangles>500000)throw std::runtime_error("world collision model");auto&list=w.collisionModels[model];list.reserve(n);for(unsigned k=0;k<n;k++){Triangle t;Point*ps[]={&t.a,&t.b,&t.c};for(auto p:ps){p->x=er.f32();p->y=er.f32();p->z=er.f32();if(fabsf(p->x)>100||fabsf(p->y)>100||fabsf(p->z)>100)throw std::runtime_error("world collision vertex");}list.push_back(t);}}if(er.p!=extra.size())throw std::runtime_error("world collision trailing");at=total;for(auto i:w.instances)if(i.layers>sets)throw std::runtime_error("world instance texture set");}if(at!=total||gpu>16*1024*1024)throw std::runtime_error("world texture budget");}
   w.marks.resize(ni);std::vector<bool> coverage(ni,false);for(auto item:w.cells){auto c=item.second;for(uint32_t j=c.first;j<c.first+c.count;j++){auto id=w.refs[j];if(w.instances[id].bounds.distance2((item.first.first+.5f)*cell,(item.first.second+.5f)*cell)>cell*cell*.5f+.1f)throw std::runtime_error("world cell location");coverage[id]=true;}}for(size_t i=0;i<ni;i++)if(bool(w.instances[i].flags&1)!=coverage[i])throw std::runtime_error("world coverage");w.metadataBytes=data;*this=std::move(w);return true;
  }catch(const std::exception& e){error=e.what();return false;}
 }
 ironasset::Mesh loadModel(uint32_t id)const{
  const auto& m=models.at(id);std::ifstream f(path.c_str(),std::ios::binary);auto bytes=read(f,m.offset,m.bytes);ironasset::Reader r(bytes);ironasset::Mesh mesh;mesh.vertices=m.vertices;mesh.frames=1;mesh.groups.reserve(m.groups);mesh.indices.reserve(m.indices);mesh.poses.reserve(m.vertices);mesh.clips.push_back({"Idle",0,1,24,true});
  for(uint32_t i=0;i<m.groups;i++){ironasset::Group g;g.start=r.u32();g.count=r.u32();g.r=r.f32();g.g=r.f32();g.b=r.f32();g.tint=r.u32();if(uint64_t(g.start)+g.count>m.indices||g.count%3||(g.tint&0xffffff)>textures.size()||(g.tint>>24)>(version==4?6u:0u)||g.r<0||g.r>1||g.g<0||g.g>1||g.b<0||g.b>1)throw std::runtime_error("world group");mesh.groups.push_back(g);}
  for(uint32_t i=0;i<m.indices;i++){uint16_t v=r.u16();if(v>=m.vertices)throw std::runtime_error("world index");mesh.indices.push_back(v);}
  for(uint32_t i=0;i<m.vertices;i++){ironasset::Vertex v;v.x=r.f32();v.y=r.f32();v.z=r.f32();v.nx=r.f32();v.ny=r.f32();v.nz=r.f32();v.u=r.f32();v.v=r.f32();if(fabsf(v.x)>100||fabsf(v.y)>100||fabsf(v.z)>100||fabsf(v.nx)>2||fabsf(v.ny)>2||fabsf(v.nz)>2)throw std::runtime_error("world vertex");mesh.poses.push_back(v);}return mesh;
 }
 std::vector<std::pair<float,uint32_t> > nearby(float x,float z,float radius){
  if(!std::isfinite(x)||!std::isfinite(z)||!std::isfinite(radius)||radius<0||radius>1000)throw std::runtime_error("world query bounds");
  if(++generation==0){std::fill(marks.begin(),marks.end(),0);generation=1;}std::vector<std::pair<float,uint32_t> > result;
  int x0=int(floorf((x-radius)/cellSize)),x1=int(floorf((x+radius)/cellSize)),z0=int(floorf((z-radius)/cellSize)),z1=int(floorf((z+radius)/cellSize));
  for(int a=x0;a<=x1;a++)for(int b=z0;b<=z1;b++){auto found=cells.find({a,b});if(found==cells.end())continue;auto c=found->second;for(uint32_t j=c.first;j<c.first+c.count;j++){uint32_t id=refs[j];if(marks[id]==generation)continue;marks[id]=generation;if(hiddenInstances.count(id))continue;float d=instances[id].bounds.distance2(x,z);if(d<=radius*radius)result.push_back({d,id});}}
  for(auto id:dynamicInstances)if(marks[id]!=generation&&!hiddenInstances.count(id)){float d=instances[id].bounds.distance2(x,z);if(d<=radius*radius)result.push_back({d,id});}
  std::sort(result.begin(),result.end());return result;
 }
 std::vector<uint32_t> lodChain(uint32_t base)const{std::vector<uint32_t> chain;for(unsigned id=base;;){chain.push_back(id);if(!models[id].finer)break;id=models[id].finer-1;}return chain;}
 Selection select(float x,float z,float radius,unsigned vertexBudget,unsigned maxModels,unsigned maxDraws,size_t cacheBudget=32*1024*1024,const Selection* previous=nullptr,bool (*renderFilter)(unsigned,const Bounds&)=nullptr){
  Selection s;
  for(auto candidate:nearby(x,z,radius)){
   uint32_t id=candidate.second;
   if(renderFilter&&!renderFilter(id,instances[id].bounds))continue;
   auto chain=lodChain(instances[id].model);float distance=sqrtf(candidate.first);int top=int(chain.size())-1;
   int wanted=distance<lodNear?top:(distance<lodMid?std::max(0,top-1):0);
   // Preserve the chosen detail around thresholds, rather than reloading on tiny movements.
   if(previous){auto found=previous->byInstance.find(id);if(found!=previous->byInstance.end()){auto where=std::find(chain.begin(),chain.end(),found->second);if(where!=chain.end()){int old=int(where-chain.begin());float threshold=(old==top||wanted==top)?lodNear:lodMid;if(old<wanted&&distance>threshold*.9f)wanted=old;else if(old>wanted&&distance<threshold*1.1f)wanted=old;}}}
   for(int rank=wanted;rank>=0;rank--){
    uint32_t mid=chain[rank];const auto& m=models[mid];size_t bytes=size_t(m.vertices)*128+size_t(m.indices)*6+size_t(m.groups)*64+1024;bool fresh=!s.models.count(mid);
    if((fresh&&s.bytes+bytes>cacheBudget)||s.vertices+m.vertices>vertexBudget||s.draws+m.groups>maxDraws||(fresh&&s.models.size()>=maxModels))continue;
    s.instances.push_back(id);s.modelForInstance.push_back(mid);s.byInstance[id]=mid;if(fresh)s.bytes+=bytes;s.models.insert(mid);s.vertices+=m.vertices;s.draws+=m.groups;
    if(version>=2&&rank==top)s.detailed++;else if(rank>0)s.medium++;else s.coarse++;break;
   }
  }
  return s;
 }
 unsigned materialTexture(unsigned tag,const Instance&i)const{unsigned base=tag&0xffffff,slot=tag>>24;if(version<4||!i.layers||slot>3)return base;const auto&set=textureSets.at(i.layers-1);unsigned selected=set[0]?set[0]:base;if(slot&&set[slot-1])selected=set[slot-1];return selected;}
 bool setVisible(unsigned id,bool visible){if(id>=instances.size()||!(instances[id].flags&1))return false;if(visible)return hiddenInstances.erase(id)!=0;return hiddenInstances.insert(id).second;}
 bool setModel(unsigned id,unsigned model){if(id>=instances.size()||model>=models.size()||!(instances[id].flags&1))return false;auto&i=instances[id];if(i.model==model)return false;i.model=model;float matrix[12];memcpy(matrix,i.transform,sizeof(matrix));return setTransform(id,matrix,true);}
 bool setTransform(unsigned id,const float*matrix,bool force=false){if(id>=instances.size()||!matrix)return false;for(int k=0;k<12;k++)if(!std::isfinite(matrix[k])||fabsf(matrix[k])>1e7f)return false;auto&i=instances[id];if(!force&&!memcmp(i.transform,matrix,12*sizeof(float)))return false;
  auto cached=modelBounds.find(i.model);if(cached==modelBounds.end()){auto mesh=loadModel(i.model);Bounds b;for(int k=0;k<3;k++){b.lo[k]=1e30f;b.hi[k]=-1e30f;}auto add=[&](Point p){float v[]={p.x,p.y,p.z};for(int k=0;k<3;k++){b.lo[k]=std::min(b.lo[k],v[k]);b.hi[k]=std::max(b.hi[k],v[k]);}};for(const auto&v:mesh.poses)add({v.x,v.y,v.z});auto col=collisionModels.find(i.model);if(col!=collisionModels.end())for(auto t:col->second){add(t.a);add(t.b);add(t.c);}cached=modelBounds.emplace(i.model,b).first;}
  memcpy(i.transform,matrix,12*sizeof(float));for(int k=0;k<3;k++){i.bounds.lo[k]=1e30f;i.bounds.hi[k]=-1e30f;}const auto&b=cached->second;for(int corner=0;corner<8;corner++){auto p=transform(i,Point((corner&1)?b.hi[0]:b.lo[0],(corner&2)?b.hi[1]:b.lo[1],(corner&4)?b.hi[2]:b.lo[2]));float v[]={p.x,p.y,p.z};for(int k=0;k<3;k++){i.bounds.lo[k]=std::min(i.bounds.lo[k],v[k]);i.bounds.hi[k]=std::max(i.bounds.hi[k],v[k]);}}dynamicInstances.insert(id);return true;}
 Point transform(const Instance&i,Point p)const{const float*m=i.transform;return {m[0]*p.x+m[1]*p.y+m[2]*p.z+m[3],m[4]*p.x+m[5]*p.y+m[6]*p.z+m[7],m[8]*p.x+m[9]*p.y+m[10]*p.z+m[11]};}
 Triangle transform(const Instance&i,const Triangle&t)const{return {transform(i,t.a),transform(i,t.b),transform(i,t.c)};}
 std::vector<Triangle> collisionTriangles(float x,float y,float z,float radius){std::vector<Triangle>out;for(auto c:nearby(x,z,radius)){const auto&i=instances[c.second];if(!(i.flags&2))continue;auto found=collisionModels.find(i.model);if(found==collisionModels.end())continue;for(const auto&local:found->second){auto t=transform(i,local);float minx=std::min(t.a.x,std::min(t.b.x,t.c.x)),maxx=std::max(t.a.x,std::max(t.b.x,t.c.x)),minz=std::min(t.a.z,std::min(t.b.z,t.c.z)),maxz=std::max(t.a.z,std::max(t.b.z,t.c.z)),miny=std::min(t.a.y,std::min(t.b.y,t.c.y)),maxy=std::max(t.a.y,std::max(t.b.y,t.c.y));if(x+radius>=minx&&x-radius<=maxx&&z+radius>=minz&&z-radius<=maxz&&y+4>=miny&&y-4<=maxy)out.push_back(t);}}return out;}
 float raycast(Point origin,Point direction,float limit,unsigned ignore=0xffffffffu){float nearest=limit;for(auto c:nearby(origin.x,origin.z,std::min(500.f,limit))){const auto&i=instances[c.second];if(c.second==ignore||!(i.flags&2))continue;float near=0,far=nearest;float o[]={origin.x,origin.y,origin.z},d[]={direction.x,direction.y,direction.z};bool hit=true;for(int k=0;k<3;k++){if(fabsf(d[k])<1e-8f){if(o[k]<i.bounds.lo[k]||o[k]>i.bounds.hi[k]){hit=false;break;}}else{float a=(i.bounds.lo[k]-o[k])/d[k],b=(i.bounds.hi[k]-o[k])/d[k];if(a>b)std::swap(a,b);near=std::max(near,a);far=std::min(far,b);if(near>far){hit=false;break;}}}if(!hit)continue;auto found=collisionModels.find(i.model);if(found!=collisionModels.end())for(const auto&t:found->second){float at=rayTriangle(origin,direction,transform(i,t),nearest);if(at>.02f)nearest=std::min(nearest,at);}}return nearest;}
 std::vector<Bounds> collision(float x,float z,float radius,unsigned maxBoxes){std::vector<Bounds> result;for(auto c:nearby(x,z,radius))if(instances[c.second].flags&2){result.push_back(instances[c.second].bounds);if(result.size()>=maxBoxes)break;}return result;}
};
}
#endif


