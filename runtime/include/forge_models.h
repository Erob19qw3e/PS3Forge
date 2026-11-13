#ifndef FORGE_MODELS_H
#define FORGE_MODELS_H
#include <map>
#include <new>
static std::map<std::string,ironasset::Mesh*> modelCache;
static ironasset::Mesh* loadForgeMesh(const std::string& asset){
 if(asset.empty())return nullptr;auto cached=modelCache.find(asset);if(cached!=modelCache.end())return cached->second;
 ironasset::Mesh* mesh=new ironasset::Mesh();std::string error;if(!mesh->load((std::string(forge::rootPath)+asset).c_str(),error)){forge::lastError=asset+" / Load: "+error;stage(forge::lastError.c_str());delete mesh;return nullptr;}
 modelCache[asset]=mesh;forge::metrics.assetBytes+=mesh->poses.capacity()*sizeof(ironasset::Vertex)+mesh->skin.capacity()*sizeof(ironasset::SkinVertex)+mesh->keys.capacity()*sizeof(std::array<float,10>)+mesh->indices.capacity()*2+mesh->bones.capacity()*sizeof(ironasset::Bone);return mesh;
}
static void sampleEntityBones(forge::Entity& e){
 e.bones.clear();auto found=modelCache.find(e.asset);if(found==modelCache.end()||found->second->bones.empty())return;auto mesh=found->second;std::vector<forgemath::Matrix> world;float alpha=e.animationBlendDuration>0?std::min(1.f,e.animationBlendTime/e.animationBlendDuration):1;
 mesh->boneMatrices(mesh->clip(e.animation.c_str()),e.animationTime,world,e.previousAnimation.empty()?-1:mesh->clip(e.previousAnimation.c_str()),e.previousAnimationTime,alpha);for(size_t i=0;i<world.size();i++)e.bones[mesh->bones[i].name]=world[i];
}
struct ForgeModel {
 ironasset::Mesh* model;S3DVertex* buffer[2];u16* indices;
 std::vector<ironasset::Vertex> pose,target,previous;std::string clip;float blend;bool initialized=false;
 ForgeModel():model(nullptr),indices(nullptr),blend(1){buffer[0]=buffer[1]=nullptr;}
 void init(const std::string& asset,unsigned vertexCapacity=0,unsigned indexCapacity=0){
  initialized=true;
  if(asset.empty())return;
  model=loadForgeMesh(asset);if(!model)return;vertexCapacity=std::max(vertexCapacity,model->vertices);indexCapacity=std::max(indexCapacity,unsigned(model->indices.size()));indices=(u16*)rsxMemalign(128,indexCapacity*sizeof(u16));
  if(!indices){stage("model indices allocation failed");exit(1);}memcpy(indices,model->indices.data(),model->indices.size()*sizeof(u16));
  for(int b=0;b<2;b++){buffer[b]=(S3DVertex*)rsxMemalign(128,vertexCapacity*sizeof(S3DVertex));if(!buffer[b]){stage("model vertex allocation failed");exit(1);}for(unsigned i=0;i<vertexCapacity;i++)new(&buffer[b][i])S3DVertex();}forge::metrics.gpuBytes+=indexCapacity*2+vertexCapacity*sizeof(S3DVertex)*2;
 }
 void draw(const forge::Entity& e,const Matrix4& transform,float dt){
  auto lod=e.features.find("LOD");if(lod!=e.features.end()){
   forge::Vec3 delta=e.position+forge::cameraPosition*(-1);float distance=sqrtf(delta.x*delta.x+delta.y*delta.y+delta.z*delta.z);auto max=lod->second.numbers.find("maxDistance");if(max!=lod->second.numbers.end()&&distance>max->second)return;std::string chosen=e.asset;for(auto& level:lod->second.lods)if(distance>=level.distance)chosen=level.asset;
   auto selected=loadForgeMesh(chosen);if(selected&&selected!=model){model=selected;memcpy(indices,model->indices.data(),model->indices.size()*sizeof(u16));previous.clear();clip.clear();}
  }
  if(!model){forge::Vec3 color=e.color;if(!e.materials.empty()&&e.materials[0].texture!=-2){bindMaterialTexture(e.materials[0].texture);color.x*=e.materials[0].color.x;color.y*=e.materials[0].color.y;color.z*=e.materials[0].color.z;}else bindForgeTexture(false);box(transform,color.x,color.y,color.z);return;}
  if(clip!=e.animation){clip=e.animation;previous=pose;blend=previous.empty()?1:0;}
  blend=e.animationBlendDuration>0?std::min(1.f,blend+dt/e.animationBlendDuration):1;
  if(!model->bones.empty()){
   std::vector<forgemath::Matrix> world;bool complete=true;for(const auto& b:model->bones){auto found=e.bones.find(b.name);if(found==e.bones.end()){complete=false;break;}world.push_back(found->second);}
   if(!complete){float alpha=e.animationBlendDuration>0?std::min(1.f,e.animationBlendTime/e.animationBlendDuration):1;model->boneMatrices(model->clip(clip.c_str()),e.animationTime,world,e.previousAnimation.empty()?-1:model->clip(e.previousAnimation.c_str()),e.previousAnimationTime,alpha);}model->skinPose(world,target);
  }else model->sample(model->clip(clip.c_str()),e.animationTime,target);pose=target;
  if(model->bones.empty()&&blend<1&&previous.size()==pose.size())for(size_t i=0;i<pose.size();i++){auto& v=pose[i];const auto& a=previous[i];v.x=a.x+(v.x-a.x)*blend;v.y=a.y+(v.y-a.y)*blend;v.z=a.z+(v.z-a.z)*blend;v.nx=a.nx+(v.nx-a.nx)*blend;v.ny=a.ny+(v.ny-a.ny)*blend;v.nz=a.nz+(v.nz-a.nz)*blend;}
  S3DVertex* out=buffer[curr_fb];for(size_t i=0;i<pose.size();i++){const auto& v=pose[i];out[i].pos=Vector3(v.x,v.y,v.z);out[i].nrm=Vector3(v.nx,v.ny,v.nz);out[i].u=v.u;out[i].v=v.v;}__sync_synchronize();
  SMeshBuffer mesh;mesh.vertices=out;mesh.cnt_vertices=model->vertices;SMeshBuffer* old=cube;cube=&mesh;
  for(size_t i=0;i<model->groups.size();i++){const auto& g=model->groups[i];if(!g.count)continue;forge::Vec3 color(g.r*e.color.x,g.g*e.color.y,g.b*e.color.z);if(i<e.materials.size()&&e.materials[i].texture!=-2){bindMaterialTexture(e.materials[i].texture);color.x*=e.materials[i].color.x;color.y*=e.materials[i].color.y;color.z*=e.materials[i].color.z;}else bindForgeTexture(forge::useAtlas&&e.textureAtlas&&g.tint);mesh.indices=indices+g.start;mesh.cnt_indices=g.count;box(transform,color.x,color.y,color.z);}cube=old;
 }
};
static std::vector<ForgeModel> renderModels;
#endif
