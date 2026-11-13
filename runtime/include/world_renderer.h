#ifndef FORGE_WORLD_RENDERER_H
#define FORGE_WORLD_RENDERER_H
#include "world_stream.h"
static float castStreamedWorld(forge::Vec3,forge::Vec3,float);
static bool transformStreamedWorld(unsigned,const float*);
static bool visibleStreamedWorld(unsigned,bool);
static bool modelStreamedWorld(unsigned,unsigned);
static float castIgnoringStreamedWorld(forge::Vec3,forge::Vec3,float,unsigned);
struct WorldGpuModel{
 ironasset::Mesh mesh;S3DVertex* vertices=nullptr;u16* indices=nullptr;size_t cpuBytes=0,gpuBytes=0;
 ~WorldGpuModel(){if(vertices)rsxFree(vertices);if(indices)rsxFree(indices);}
};
struct ForgeWorldRenderer{
 forgeworld::World world;forgeworld::Selection selection;std::map<uint32_t,WorldGpuModel*> cache;std::vector<u32*> textureBuffers;std::vector<u32> textureOffsets;bool ready=false,selected=false;float lastX=0,lastZ=0;unsigned loads=0,evictions=0;size_t cacheBytes=0;
 forge::Vec3 anchor()const{auto e=forge::findId(forge::worldSettings.target);return e?e->position:forge::cameraPosition;}
 void init(){if(forge::worldSettings.file.empty())return;std::string error;if(!world.open(std::string(forge::rootPath)+forge::worldSettings.file,error)){forge::lastError="World sectors / "+error;stage(forge::lastError.c_str());return;}try{std::ifstream file(world.path.c_str(),std::ios::binary);for(auto t:world.textures){auto bytes=forgeworld::World::read(file,t.offset,t.size*t.size*4);u32* pixels=(u32*)rsxMemalign(128,bytes.size());if(!pixels)throw std::runtime_error("world texture allocation");memcpy(pixels,bytes.data(),bytes.size());u32 offset;rsxAddressToOffset(pixels,&offset);textureBuffers.push_back(pixels);textureOffsets.push_back(offset);forge::metrics.gpuBytes+=bytes.size();}__sync_synchronize();}catch(const std::exception& e){for(auto p:textureBuffers)rsxFree(p);textureBuffers.clear();textureOffsets.clear();forge::lastError=e.what();stage(e.what());return;}ready=true;forge::worldTransform=transformStreamedWorld;forge::worldVisible=visibleStreamedWorld;forge::worldModel=modelStreamedWorld;forge::worldRaycastIgnoring=castIgnoringStreamedWorld;if(world.version==4)forge::worldRaycast=castStreamedWorld;forge::metrics.assetBytes+=world.metadataBytes;for(const auto&entry:world.collisionModels)forge::metrics.assetBytes+=entry.second.capacity()*sizeof(forgeworld::Triangle);stage("world sector index ready");}
 void updateCollisions(){if(!ready)return;if(forge::activeScene!=forge::worldSettings.scene){forge::worldBoxes.clear();forge::worldTriangles.clear();return;}auto p=anchor();forge::worldBoxes.clear();forge::worldTriangles.clear();if(world.version==4){forge::worldTriangles=world.collisionTriangles(p.x,p.y,p.z,forge::worldSettings.collisionRadius);return;}for(auto b:world.collision(p.x,p.z,12,128))forge::worldBoxes.push_back({forge::Vec3(b.lo[0],b.lo[1],b.lo[2]),forge::Vec3(b.hi[0],b.hi[1],b.hi[2])});}
 void prepare(){
  if(!ready||forge::activeScene!=forge::worldSettings.scene)return;auto p=anchor();if(!forge::worldRenderFilter&&selected&&(p.x-lastX)*(p.x-lastX)+(p.z-lastZ)*(p.z-lastZ)<1)return;
  lastX=p.x;lastZ=p.z;selected=true;selection=world.select(p.x,p.z,forge::worldSettings.radius,forge::worldSettings.vertexBudget,forge::worldSettings.maxModels,forge::worldSettings.maxDraws,forge::worldSettings.cacheBytes,&selection,forge::worldRenderFilter);
  size_t missingBytes=0,missingModels=0;
  for(auto id:selection.models)if(!cache.count(id)){
   const auto& model=world.models[id];
   missingBytes+=size_t(model.vertices)*128+size_t(model.indices)*6+size_t(model.groups)*64+1024;
   missingModels++;
  }
  // No RSX memory may be reused until all preceding frame commands have completed.
  if(missingModels&&(!forge::worldRenderFilter||cacheBytes+missingBytes>forge::worldSettings.cacheBytes||
                     cache.size()+missingModels>forge::worldSettings.maxModels)){static uint32_t worldFence=0x60000000;rsxFinish(context,worldFence++);for(auto i=cache.begin();i!=cache.end();){if(!selection.models.count(i->first)){auto m=i->second;cacheBytes-=m->cpuBytes+m->gpuBytes;forge::metrics.assetBytes-=m->cpuBytes;forge::metrics.gpuBytes-=m->gpuBytes;delete m;i=cache.erase(i);evictions++;}else ++i;}}
  for(auto id:selection.models)if(!cache.count(id)){
   WorldGpuModel* gpu=new WorldGpuModel();try{gpu->mesh=world.loadModel(id);auto& mesh=gpu->mesh;gpu->cpuBytes=mesh.poses.capacity()*sizeof(ironasset::Vertex)+mesh.indices.capacity()*2+mesh.groups.capacity()*sizeof(ironasset::Group);gpu->gpuBytes=mesh.vertices*sizeof(S3DVertex)+mesh.indices.size()*2;
    if(cacheBytes+gpu->cpuBytes+gpu->gpuBytes>forge::worldSettings.cacheBytes)throw std::runtime_error("world resident cache budget");
    gpu->vertices=(S3DVertex*)rsxMemalign(128,mesh.vertices*sizeof(S3DVertex));gpu->indices=(u16*)rsxMemalign(128,mesh.indices.size()*2);if(!gpu->vertices||!gpu->indices)throw std::runtime_error("world RSX allocation");
    for(size_t i=0;i<mesh.poses.size();i++){const auto& v=mesh.poses[i];new(&gpu->vertices[i])S3DVertex();gpu->vertices[i].pos=Vector3(v.x,v.y,v.z);gpu->vertices[i].nrm=Vector3(v.nx,v.ny,v.nz);gpu->vertices[i].u=v.u;gpu->vertices[i].v=v.v;}memcpy(gpu->indices,mesh.indices.data(),mesh.indices.size()*2);__sync_synchronize();cacheBytes+=gpu->cpuBytes+gpu->gpuBytes;forge::metrics.assetBytes+=gpu->cpuBytes;forge::metrics.gpuBytes+=gpu->gpuBytes;cache[id]=gpu;loads++;
   }catch(const std::exception& e){delete gpu;forge::lastError=std::string("World model ")+std::to_string(id)+" / "+e.what();stage(forge::lastError.c_str());}
  }
  if(!forge::worldRenderFilter)updateCollisions();
  char status[256];snprintf(status,sizeof(status),"World: %u indexed | %u visible | %u vertices | %u/%u cached | loads %u / unloads %u | LOD %u/%u/%u",unsigned(world.instances.size()),unsigned(selection.instances.size()),selection.vertices,unsigned(cache.size()),forge::worldSettings.maxModels,loads,evictions,selection.detailed,selection.medium,selection.coarse);forge::worldStatus=status;
 }
 void bind(unsigned id){if(!id||id>textureBuffers.size()){bindForgeTexture(false);return;}u32* old=texture_buffer;u32 offset=texture_offset;texture_buffer=textureBuffers[id-1];texture_offset=textureOffsets[id-1];texture_width=world.textures[id-1].size;setTexture(textureUnit->index);texture_buffer=old;texture_offset=offset;texture_width=128;rsxTextureWrapMode(context,textureUnit->index,GCM_TEXTURE_REPEAT,GCM_TEXTURE_REPEAT,GCM_TEXTURE_CLAMP_TO_EDGE,0,GCM_TEXTURE_ZFUNC_LESS,0);atlasBound=false;boundCustom=-2;}
 void draw(){if(!ready||forge::activeScene!=forge::worldSettings.scene)return;for(size_t item=0;item<selection.instances.size();item++){auto id=selection.instances[item];const auto& instance=world.instances[id];if(world.hiddenInstances.count(id))continue;auto found=cache.find(selection.modelForInstance[item]);if(found==cache.end())continue;auto gpu=found->second;const float* m=instance.transform;Matrix4 transform(Vector4(m[0],m[4],m[8],0),Vector4(m[1],m[5],m[9],0),Vector4(m[2],m[6],m[10],0),Vector4(m[3],m[7],m[11],1));SMeshBuffer mesh;mesh.vertices=gpu->vertices;mesh.cnt_vertices=gpu->mesh.vertices;auto old=cube;cube=&mesh;bindForgeTexture(false);for(auto g:gpu->mesh.groups){if(!g.count)continue;bind(world.materialTexture(g.tint,instance));mesh.indices=gpu->indices+g.start;mesh.cnt_indices=g.count;box(transform,g.r,g.g,g.b);}cube=old;}}
};
static ForgeWorldRenderer worldRenderer;
static bool transformStreamedWorld(unsigned id,const float*m){return worldRenderer.ready&&worldRenderer.world.setTransform(id,m);}
static bool visibleStreamedWorld(unsigned id,bool visible){if(!worldRenderer.ready)return false;bool changed=worldRenderer.world.setVisible(id,visible);if(changed)worldRenderer.selected=false;return changed;}
static bool modelStreamedWorld(unsigned id,unsigned model){if(!worldRenderer.ready)return false;bool changed=worldRenderer.world.setModel(id,model);if(changed)worldRenderer.selected=false;return changed;}
static float castIgnoringStreamedWorld(forge::Vec3 o,forge::Vec3 d,float limit,unsigned ignore){if(!worldRenderer.ready||forge::activeScene!=forge::worldSettings.scene)return limit;return worldRenderer.world.raycast({o.x,o.y,o.z},{d.x,d.y,d.z},limit,ignore);}
static float castStreamedWorld(forge::Vec3 o,forge::Vec3 d,float limit){if(!worldRenderer.ready||forge::activeScene!=forge::worldSettings.scene)return limit;return worldRenderer.world.raycast({o.x,o.y,o.z},{d.x,d.y,d.z},limit);}
static void updateStreamedWorld(){worldRenderer.updateCollisions();}
#endif
