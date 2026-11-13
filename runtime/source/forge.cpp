#include "Forge.h"
#include "engine_components.h"
#include <chrono>
#include <exception>
namespace forge {
WorldSettings worldSettings;std::vector<WorldBox> worldBoxes;std::string worldStatus;void (*updateWorld)()=nullptr;
std::vector<forgeworld::Triangle> worldTriangles;float (*worldRaycast)(Vec3,Vec3,float)=nullptr;
bool (*worldTransform)(unsigned,const float*)=nullptr;
bool (*worldVisible)(unsigned,bool)=nullptr;
bool (*worldRenderFilter)(unsigned,const forgeworld::Bounds&)=nullptr;
bool (*entityRenderFilter)(const Entity&)=nullptr;
bool (*worldModel)(unsigned,unsigned)=nullptr;
float (*worldRaycastIgnoring)(Vec3,Vec3,float,unsigned)=nullptr;
std::vector<Entity> entities,initialEntities;
std::vector<std::string> sceneNames;
Vec3 cameraPosition(7,6,10),cameraTarget(0,1,0);
int activeScene=0,pendingScene=-1;
unsigned background=0xff182634;
float cameraFov=65;
float cameraAspect=16.f/9.f;
bool useAtlas=false,crosshair=false;
std::string hudText;
Metrics metrics;bool showProfiler=false;std::string lastError;void (*sampleBones)(Entity&)=nullptr;
void emit(Entity& e,const std::string& name,float v,const std::string& target){if(e.events.size()>=64)e.events.erase(e.events.begin());e.events.push_back(Event(name,e.id,target,v));}
bool pollEvent(Entity& e,const std::string& name){for(auto i=e.events.begin();i!=e.events.end();++i)if(i->name==name){e.events.erase(i);return true;}return false;}
void initialize(){worldSettings=WorldSettings();worldBoxes.clear();worldTriangles.clear();worldRaycast=nullptr;worldTransform=nullptr;worldVisible=nullptr;worldRenderFilter=nullptr;entityRenderFilter=nullptr;worldModel=nullptr;worldRaycastIgnoring=nullptr;worldStatus.clear();createProject();initialEntities=entities;}
void loadScene(int index){if(index>=0&&index<(int)sceneNames.size())pendingScene=index;}
Entity* find(const char* name){for(auto& e:entities)if(e.scene==activeScene&&e.name==name)return &e;return nullptr;}
Entity* findId(const std::string& id){for(auto& e:entities)if(e.scene==activeScene&&e.id==id)return &e;return nullptr;}
static float hx(const Entity& e){return radiusX(e);}
static float hz(const Entity& e){return e.features.count("CharacterController")?hx(e):e.scale.z*(e.asset.empty()?.5f:.35f);}
static float height(const Entity& e){return entityHeight(e);}
static float bottom(const Entity& e){return entityBottom(e);}
static bool overlap(const Entity& a,const Entity& b){return fabsf(a.position.x-b.position.x)<hx(a)+hx(b)&&fabsf(a.position.z-b.position.z)<hz(a)+hz(b)&&bottom(a)<bottom(b)+height(b)&&bottom(a)+height(a)>bottom(b);}
void step(const Input& input,float dt){
 if(!std::isfinite(dt)||dt<=0)return;
 auto begin=std::chrono::steady_clock::now();
 if(pendingScene>=0){activeScene=pendingScene;pendingScene=-1;for(size_t i=0;i<entities.size();i++)if(entities[i].scene==activeScene)entities[i]=initialEntities[i];}
 if(updateWorld)updateWorld();
 for(auto& e:entities){
  if(e.scene!=activeScene)continue;
  Vec3 previous=e.position;
  float previousBottom=bottom(e);
  builtinsBefore(e,input,dt);
  try{if(e.script)e.script(e,input,dt);}catch(const std::exception& error){lastError=e.name+" / "+(e.scriptLabel.empty()?"C++ script":e.scriptLabel)+": "+error.what();emit(e,"ScriptError");}
  if(!std::isfinite(e.position.x)||!std::isfinite(e.position.y)||!std::isfinite(e.position.z)){lastError=e.name+" / Transform: non-finite position";e.position=previous;e.velocity=Vec3();emit(e,"TransformError");}
  e.started=true;e.animationTime+=dt;e.animationBlendTime+=dt;if(!e.previousAnimation.empty()){e.previousAnimationTime+=dt;if(e.animationBlendTime>=e.animationBlendDuration)e.previousAnimation.clear();}
  if(e.gravity){
  e.velocity.y-=9.81f*dt;e.position=e.position+e.velocity*dt;e.grounded=false;
  if(e.collider){
   for(const auto& other:entities){
    if(&other==&e||other.scene!=activeScene||!other.collider||other.gravity||!overlap(e,other))continue;
    float oldBottom=previousBottom,top=bottom(other)+height(other);
    if(oldBottom>=top-.08f&&e.velocity.y<=0){e.position.y=top+((e.asset.empty()&&!e.features.count("CharacterController"))?height(e)*.5f:0);e.velocity.y=0;e.grounded=true;}
    else {float dx=hx(e)+hx(other)-fabsf(e.position.x-other.position.x),dz=hz(e)+hz(other)-fabsf(e.position.z-other.position.z);if(dx<dz)e.position.x+=(e.position.x>=other.position.x?dx:-dx);else e.position.z+=(e.position.z>=other.position.z?dz:-dz);}
   }
   for(const auto& box:worldBoxes){
    if(e.position.x+hx(e)<=box.lo.x||e.position.x-hx(e)>=box.hi.x||e.position.z+hz(e)<=box.lo.z||e.position.z-hz(e)>=box.hi.z||bottom(e)>=box.hi.y||bottom(e)+height(e)<=box.lo.y)continue;
    if(previousBottom>=box.hi.y-.08f&&e.velocity.y<=0){e.position.y=box.hi.y+((e.asset.empty()&&!e.features.count("CharacterController"))?height(e)*.5f:0);e.velocity.y=0;e.grounded=true;}
    else{float cx=(box.lo.x+box.hi.x)*.5f,cz=(box.lo.z+box.hi.z)*.5f,dx=(box.hi.x-box.lo.x)*.5f+hx(e)-fabsf(e.position.x-cx),dz=(box.hi.z-box.lo.z)*.5f+hz(e)-fabsf(e.position.z-cz);if(dx<dz)e.position.x+=(e.position.x>=cx?dx:-dx);else e.position.z+=(e.position.z>=cz?dz:-dz);}
   }
  }
  if(e.collider&&!worldTriangles.empty()){
   bool centered=e.asset.empty()&&!e.features.count("CharacterController");float offset=centered?0:height(e)*.5f,half=height(e)*.5f,radius=std::max(.05f,std::min(hx(e),half));forgeworld::Point center(e.position.x,e.position.y+offset,e.position.z),prior(previous.x,previous.y+offset,previous.z);
   for(int pass=0;pass<3;pass++)for(const auto&t:worldTriangles){forgeworld::Point n;float penetration;if(forgeworld::capsuleContact(center,prior,radius,half,t,n,penetration)){
    if(e.stableGround&&n.y>.65f&&e.velocity.y<=0){
     // Resolve walkable support vertically: normal projection turns gravity
     // into downhill velocity and pushes a directly controlled walker back.
     center.y+=(penetration+.0001f)/n.y;e.velocity.y=0;e.grounded=true;
    }else{
     center=center+n*(penetration+.0001f);float inward=e.velocity.x*n.x+e.velocity.y*n.y+e.velocity.z*n.z;
     if(inward<0){e.velocity.x-=n.x*inward;e.velocity.y-=n.y*inward;e.velocity.z-=n.z*inward;}
     if(n.y>.65f)e.grounded=true;
    }
   }}
   e.position=Vec3(center.x,center.y-offset,center.z);
  }
  if(bottom(e)<0){e.position.y=(e.asset.empty()&&!e.features.count("CharacterController"))?height(e)*.5f:0;e.velocity.y=0;e.grounded=true;}
  }
  float dx=e.position.x-previous.x,dz=e.position.z-previous.z;e.parameters["Speed"]=sqrtf(dx*dx+dz*dz)/dt;e.parameters["Moving"]=e.parameters["Speed"]>.05f;e.parameters["Grounded"]=e.grounded;e.parameters["Health"]=e.health;
 }
 for(auto& e:entities)if(e.scene==activeScene){animateComponents(e);if(sampleBones)sampleBones(e);}
 builtinsAfter(input,dt);std::set<std::string> visiting,done;for(auto& e:entities)if(e.scene==activeScene)resolveAttachment(e,visiting,done);
 metrics.logicMs=std::chrono::duration<float,std::milli>(std::chrono::steady_clock::now()-begin).count();
}
}
