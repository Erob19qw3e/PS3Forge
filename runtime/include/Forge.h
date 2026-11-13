#ifndef PS3_FORGE_H
#define PS3_FORGE_H
#include <cmath>
#include <algorithm>
#include <vector>
#include <string>
#include <map>
#include "forge_math.h"
#include "world_collision.h"
namespace forgeworld { struct Bounds; }
namespace forge {
struct Vec3 { float x,y,z; Vec3(float X=0,float Y=0,float Z=0):x(X),y(Y),z(Z){} Vec3 operator+(const Vec3& b)const{return Vec3(x+b.x,y+b.y,z+b.z);} Vec3 operator*(float a)const{return Vec3(x*a,y*a,z*a);} };
struct Input {float moveX,moveY,lookX,lookY;bool cross,square,triangle,r1,l1,crossHeld,fireHeld,aimHeld,sprint;Input():moveX(0),moveY(0),lookX(0),lookY(0),cross(false),square(false),triangle(false),r1(false),l1(false),crossHeld(false),fireHeld(false),aimHeld(false),sprint(false){}};
struct Entity;
struct LODLevel{float distance;std::string asset;LODLevel(float d,const std::string& a):distance(d),asset(a){}};
struct AnimationState{std::string name,clip;AnimationState(const std::string& n,const std::string& c):name(n),clip(c){}};
struct AnimationTransition{std::string from,to,parameter,op;float value,blend;AnimationTransition(const std::string& f,const std::string& t,const std::string& p,const std::string& o,float v,float b):from(f),to(t),parameter(p),op(o),value(v),blend(b){}};
struct ClipInfo{float duration;bool loop;ClipInfo(float d=1,bool l=true):duration(d),loop(l){}};
struct ClipEvent{std::string clip,name;float time;ClipEvent(const std::string& c,float t,const std::string& n):clip(c),name(n),time(t){}};
struct Feature{std::map<std::string,float> numbers;std::map<std::string,std::string> strings;std::map<std::string,Vec3> vectors;std::vector<Vec3> points;std::vector<LODLevel> lods;std::vector<AnimationState> states;std::vector<AnimationTransition> transitions;};
struct Event{std::string name,source,target;float value;Event(const std::string& n,const std::string& s,const std::string& t,float v):name(n),source(s),target(t),value(v){}};
struct MaterialBinding{int texture;Vec3 color;MaterialBinding(int t=-1,Vec3 c=Vec3(1,1,1)):texture(t),color(c){}};
struct Metrics{float logicMs=0,submitMs=0,flipMs=0,frameMs=0;unsigned drawCalls=0,triangles=0;size_t assetBytes=0,gpuBytes=0;};
typedef void (*Script)(Entity&,const Input&,float);
struct Entity {
 std::map<std::string,float> scriptValues,scriptState;
 float health=100,maxHealth=100;
 float renderRadius=0;
 bool textureAtlas=false;
 // Walking characters keep their horizontal intent on walkable slopes.
 // Opt-in: other entities retain their existing sliding physics.
 bool stableGround=false;
 std::string id,debugState,animatorState,previousAnimation,lastEventClip;float previousAnimationTime=0,animationBlendTime=1,animationBlendDuration=.12f,lastEventTime=0;
 std::map<std::string,Feature> features;std::map<std::string,float> parameters;std::map<std::string,ClipInfo> clipInfo;std::vector<ClipEvent> animationEvents;std::vector<Event> events;
 std::map<std::string,forgemath::Matrix> bones;std::vector<MaterialBinding> materials;std::vector<Vec3> navPath;size_t navCursor=0;unsigned meshCapacity=0,indexCapacity=0;
 std::string name,asset,animation,scriptLabel;Vec3 position,rotation,scale,color,velocity;int scene;bool collider,gravity,grounded,started,visible,viewModel;float animationTime;Script script;
 Entity():animation("Idle"),scale(1,1,1),color(1,1,1),scene(0),collider(false),gravity(false),grounded(false),started(false),visible(true),viewModel(false),animationTime(0),script(nullptr){}
 void play(const char* clip){if(animation!=clip){previousAnimation=animation;previousAnimationTime=animationTime;animationBlendTime=0;animation=clip;animationTime=0;}}
};
struct WorldSettings{std::string file,target;int scene=0;float radius=150,collisionRadius=12;unsigned vertexBudget=38000,maxModels=24,maxDraws=350,cacheBytes=16*1024*1024;Script renderPolicy=nullptr;};
struct WorldBox{Vec3 lo,hi;};
extern WorldSettings worldSettings;extern std::vector<WorldBox> worldBoxes;extern std::string worldStatus;extern void (*updateWorld)();
extern std::vector<forgeworld::Triangle> worldTriangles;
extern float (*worldRaycast)(Vec3,Vec3,float);
extern bool (*worldTransform)(unsigned,const float*);
extern bool (*worldVisible)(unsigned,bool);
extern bool (*worldRenderFilter)(unsigned,const forgeworld::Bounds&);
extern bool (*entityRenderFilter)(const Entity&);
extern bool (*worldModel)(unsigned,unsigned);
extern float (*worldRaycastIgnoring)(Vec3,Vec3,float,unsigned);
extern std::vector<Entity> entities;
extern std::vector<std::string> sceneNames;
extern Vec3 cameraPosition,cameraTarget;
extern int activeScene;
extern unsigned background;
extern float cameraFov;
extern float cameraAspect;
extern bool useAtlas, crosshair;
extern std::string hudText;
extern Metrics metrics;
extern bool showProfiler;
extern std::string lastError;
extern void (*sampleBones)(Entity&);
extern const char* rootPath;
void createProject();
void initialize();
void step(const Input&,float dt);
void loadScene(int index);
Entity* find(const char* name);
Entity* findId(const std::string& id);
void emit(Entity& object,const std::string& name,float value=0,const std::string& target="");
bool pollEvent(Entity& object,const std::string& name);
}
#include "ForgeScript.h"
#endif
