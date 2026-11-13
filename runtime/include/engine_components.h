#ifndef FORGE_ENGINE_COMPONENTS_H
#define FORGE_ENGINE_COMPONENTS_H
#include <queue>
#include <limits>
#include <set>
namespace forge {
inline Feature* feature(Entity& e,const char* name){auto it=e.features.find(name);return it==e.features.end()?nullptr:&it->second;}
inline float value(const Feature& f,const char* n,float fallback=0){auto i=f.numbers.find(n);return i==f.numbers.end()?fallback:i->second;}
inline float distance(const Vec3& a,const Vec3& b){float x=a.x-b.x,y=a.y-b.y,z=a.z-b.z;return sqrtf(x*x+y*y+z*z);}
inline float radiusX(const Entity& e){auto i=e.features.find("CharacterController");return i==e.features.end()?e.scale.x*(e.asset.empty()?.5f:.35f):i->second.numbers.at("radius");}
inline float entityHeight(const Entity& e){auto i=e.features.find("CharacterController");if(i!=e.features.end()){auto c=e.scriptState.find("$crouch");return i->second.numbers.at(c!=e.scriptState.end()&&c->second?"crouchHeight":"height");}return e.scale.y*(e.asset.empty()?1:2.2f);}
inline float entityBottom(const Entity& e){return e.features.count("CharacterController")?e.position.y:e.position.y-(e.asset.empty()?entityHeight(e)*.5f:0);}
inline float rayBox(const Vec3& origin,const Vec3& direction,const Entity& e,float maximum,float expand=0){
 float a=0,b=maximum;float o[]={origin.x,origin.y,origin.z},d[]={direction.x,direction.y,direction.z};float hx=radiusX(e)+expand,hz=e.features.count("CharacterController")?hx:e.scale.z*(e.asset.empty()?.5f:.35f)+expand;float lo[]={e.position.x-hx,entityBottom(e)-expand,e.position.z-hz},hi[]={e.position.x+hx,entityBottom(e)+entityHeight(e)+expand,e.position.z+hz};
 for(int n=0;n<3;n++){if(fabsf(d[n])<1e-7f){if(o[n]<lo[n]||o[n]>hi[n])return maximum+1;}else{float x=(lo[n]-o[n])/d[n],y=(hi[n]-o[n])/d[n];if(x>y)std::swap(x,y);a=std::max(a,x);b=std::min(b,y);if(a>b)return maximum+1;}}return a;
}
inline bool lineOfSight(const Entity& from,const Entity& to){Vec3 o=from.position+Vec3(0,.9f,0),end=to.position+Vec3(0,.9f,0),delta=end+o*(-1);float length=distance(end,o);if(length<.001f)return true;for(const auto& e:entities)if(&e!=&from&&&e!=&to&&e.scene==activeScene&&e.collider&&!e.gravity&&entityBottom(e)+entityHeight(e)>.2f&&rayBox(o,delta*(1/length),e,length)<length)return false;return true;}
inline void applyDamage(Entity& target,float amount,const Entity& source){if(!feature(target,"Health")||target.health<=0||amount<=0)return;target.health=std::max(0.f,target.health-amount);emit(target,"Damaged",amount,source.id);if(target.health<=0){emit(target,"Died",0,source.id);target.debugState="Dead";target.velocity=Vec3();if(value(*feature(target,"Health"),"hideOnDeath"))target.visible=false;}}
inline void navigationPath(Entity& agent,const Vec3& goal,Feature& nav){
 int size=int(value(nav,"gridSize",64));float cell=value(nav,"cellSize",1),extent=size*cell*.5f,radius=value(nav,"radius",.35f);int total=size*size;
 auto index=[&](float x,float z){int a=std::max(0,std::min(size-1,int(floorf((x+extent)/cell)))),b=std::max(0,std::min(size-1,int(floorf((z+extent)/cell))));return b*size+a;};
 std::vector<unsigned char> blocked(total,0);
 for(int n=0;n<total;n++){float x=(n%size+.5f)*cell-extent,z=(n/size+.5f)*cell-extent;for(const auto& e:entities){if(&e==&agent||e.scene!=activeScene||!e.collider||e.gravity||entityBottom(e)+entityHeight(e)<=.2f)continue;float hx=radiusX(e)+radius,hz=e.scale.z*(e.asset.empty()?.5f:.35f)+radius;if(fabsf(x-e.position.x)<hx&&fabsf(z-e.position.z)<hz){blocked[n]=1;break;}}}
 int start=index(agent.position.x,agent.position.z),finish=index(goal.x,goal.z);blocked[start]=0;
 if(blocked[finish]){int nearest=-1;float score=1e30f;for(int n=0;n<total;n++)if(!blocked[n]){float d=float((n%size-finish%size)*(n%size-finish%size)+(n/size-finish/size)*(n/size-finish/size));if(d<score){score=d;nearest=n;}}if(nearest<0)return;finish=nearest;}
 std::vector<float> costs(total,1e30f);std::vector<int> parents(total,-1);std::priority_queue<std::pair<float,int>,std::vector<std::pair<float,int> >,std::greater<std::pair<float,int> > > open;costs[start]=0;open.push({0,start});std::vector<unsigned char> closed(total,0);
 while(!open.empty()){int n=open.top().second;open.pop();if(closed[n])continue;closed[n]=1;if(n==finish)break;int x=n%size,z=n/size;const int dx[]={-1,1,0,0},dz[]={0,0,-1,1};for(int k=0;k<4;k++){int xx=x+dx[k],zz=z+dz[k];if(xx<0||zz<0||xx>=size||zz>=size)continue;int next=zz*size+xx;if(blocked[next]||costs[n]+1>=costs[next])continue;costs[next]=costs[n]+1;parents[next]=n;open.push({costs[next]+float(abs(xx-finish%size)+abs(zz-finish/size)),next});}}
 agent.navPath.clear();agent.navCursor=0;if(start!=finish&&parents[finish]<0){agent.debugState="PathBlocked";emit(agent,"PathBlocked");return;}
 std::vector<int> path;for(int n=finish;n!=start&&n>=0;n=parents[n])path.push_back(n);std::reverse(path.begin(),path.end());for(int n:path)agent.navPath.push_back(Vec3((n%size+.5f)*cell-extent,agent.position.y,(n/size+.5f)*cell-extent));
 if(!blocked[index(goal.x,goal.z)])agent.navPath.push_back(Vec3(goal.x,agent.position.y,goal.z));
}
inline void builtinsBefore(Entity& e,const Input& input,float dt){
 if(!e.started){if(auto h=feature(e,"Health")){e.maxHealth=value(*h,"maxHealth",100);e.health=e.maxHealth;}if(auto c=feature(e,"CharacterController")){e.scriptState["$firstPerson"]=value(*c,"firstPerson",1);e.collider=e.gravity=true;}if(auto w=feature(e,"Weapon"))e.scriptState["$ammo"]=value(*w,"magazine",24);}
 if(feature(e,"Health")&&e.health<=0)return;
 if(auto c=feature(e,"CharacterController")){
  if(input.triangle)e.scriptState["$firstPerson"]=!e.scriptState["$firstPerson"];
  if(input.r1&&e.grounded)e.scriptState["$crouch"]=!e.scriptState["$crouch"];
  float& yaw=e.scriptState["$yaw"];float& pitch=e.scriptState["$pitch"];yaw+=input.lookX*2.2f*dt;pitch=std::max(-1.15f,std::min(1.15f,pitch+input.lookY*1.7f*dt));
  float x=input.moveX,z=input.moveY,length=sqrtf(x*x+z*z);if(length>1){x/=length;z/=length;}bool crouch=e.scriptState["$crouch"]!=0,sprint=input.sprint&&!crouch&&!input.aimHeld&&z>.5f;float speed=value(*c,crouch?"walkSpeed":sprint?"sprintSpeed":length>.6f&&!input.aimHeld?"runSpeed":"walkSpeed",2);if(crouch)speed*=.65f;
  e.position.x+=(cosf(yaw)*x+sinf(yaw)*z)*speed*dt;e.position.z+=(sinf(yaw)*x-cosf(yaw)*z)*speed*dt;e.rotation.y=-yaw*57.2957795f;
  if(input.cross&&e.grounded&&!crouch)e.velocity.y=value(*c,"jumpSpeed",4.5f);
  e.parameters["Sprint"]=sprint;e.parameters["Crouch"]=crouch;
 }
 if(auto nav=feature(e,"NavigationAgent")){
  Vec3 goal=nav->vectors["goal"];bool move=true;auto npc=feature(e,"NPC");
  if(npc){
   Entity* target=findId(npc->strings["target"]);float range=target?distance(e.position,target->position):1e30f;bool sees=target&&target->health>0&&range<=value(*npc,"detectionRange",10)&&lineOfSight(e,*target);
   if(sees){goal=target->position;e.debugState="Chase";if(range<=value(*npc,"attackRange",2)){move=false;e.debugState="Attack";e.scriptState["$attack"]-=dt;if(e.scriptState["$attack"]<=0){applyDamage(*target,value(*npc,"damage",10),e);emit(e,"Attack",value(*npc,"damage",10),target->id);e.scriptState["$attack"]=value(*npc,"attackInterval",1);}}}
   else if(!npc->points.empty()){size_t n=size_t(e.scriptState["$patrol"])%npc->points.size();goal=npc->points[n];if(distance(e.position,goal)<.4f)e.scriptState["$patrol"]=float((n+1)%npc->points.size());e.debugState="Patrol";}else{move=false;e.debugState="Idle";}
  }
  if(move){e.scriptState["$repath"]-=dt;if(e.scriptState["$repath"]<=0){navigationPath(e,goal,*nav);e.scriptState["$repath"]=value(*nav,"repathInterval",.5f);}
   if(e.navCursor<e.navPath.size()){Vec3 target=e.navPath[e.navCursor],delta=target+e.position*(-1);delta.y=0;float length=sqrtf(delta.x*delta.x+delta.z*delta.z),step=value(*nav,"speed",2)*dt;if(length<=step+.03f){e.position.x=target.x;e.position.z=target.z;e.navCursor++;}else{e.position=e.position+delta*(step/length);e.rotation.y=-atan2f(delta.x,-delta.z)*57.2957795f;}}else if(e.debugState!="PathBlocked")e.debugState=npc?e.debugState:"Arrived";
  }
 }
}
inline bool condition(float x,const std::string& op,float y){if(op==">")return x>y;if(op==">=")return x>=y;if(op=="<")return x<y;if(op=="<=")return x<=y;if(op=="==")return fabsf(x-y)<1e-5f;return fabsf(x-y)>=1e-5f;}
inline void animateComponents(Entity& e){
 if(auto graph=feature(e,"Animator")){
  if(e.animatorState.empty()){e.animatorState=graph->strings["initial"];for(auto& s:graph->states)if(s.name==e.animatorState)e.play(s.clip.c_str());}
  for(const auto& t:graph->transitions)if((t.from=="*"||t.from==e.animatorState)&&t.to!=e.animatorState&&condition(e.parameters[t.parameter],t.op,t.value)){e.animatorState=t.to;e.animationBlendDuration=t.blend;for(const auto& s:graph->states)if(s.name==t.to)e.play(s.clip.c_str());break;}
 }
 bool changed=e.lastEventClip!=e.animation;float from=changed?0:e.lastEventTime,to=e.animationTime;if(to<from)from=0;auto info=e.clipInfo.find(e.animation);
 if(info!=e.clipInfo.end())for(const auto& event:e.animationEvents)if(event.clip==e.animation){float duration=info->second.duration;int a=info->second.loop?int(floorf(from/duration)):0,b=info->second.loop?int(floorf(to/duration)):0;for(int k=a;k<=std::min(b,a+16);k++){float t=event.time+k*duration;if((t>from||(changed&&t==0))&&t<=to)emit(e,event.name);}}
 e.lastEventClip=e.animation;e.lastEventTime=to;
}
inline void resolveAttachment(Entity& e,std::set<std::string>& visiting,std::set<std::string>& done){
 auto c=feature(e,"Attachment");if(!c||done.count(e.id))return;if(!visiting.insert(e.id).second){lastError=e.name+" / Attachment: cycle";return;}Entity* target=findId(c->strings["target"]);if(target){resolveAttachment(*target,visiting,done);auto bone=target->bones.find(c->strings["bone"]);if(bone!=target->bones.end()){
  Vec3 o=c->vectors["offset"],r=c->vectors["rotation"],s=c->vectors["scale"];
  auto world=forgemath::euler(target->position.x,target->position.y,target->position.z,target->rotation.x,target->rotation.y,target->rotation.z,target->scale.x,target->scale.y,target->scale.z)*bone->second*forgemath::euler(o.x,o.y,o.z,r.x,r.y,r.z,s.x,s.y,s.z);float t[3],angles[3],scale[3];forgemath::decompose(world,t,angles,scale);e.position=Vec3(t[0],t[1],t[2]);e.rotation=Vec3(angles[0],angles[1],angles[2]);e.scale=Vec3(scale[0],scale[1],scale[2]);if(value(*c,"inheritVisibility",1))e.visible=target->visible;
 }else lastError=e.name+" / Attachment: missing bone "+c->strings["bone"];}
 visiting.erase(e.id);done.insert(e.id);
}
inline void builtinsAfter(const Input& input,float dt){
 for(auto& e:entities)if(e.scene==activeScene)if(auto c=feature(e,"CameraFollow")){
  e.visible=false;auto target=findId(c->strings["target"]);if(!target)continue;bool cc=feature(*target,"CharacterController")!=nullptr;
  if(!cc&&input.triangle&&value(*c,"allowToggle",1))e.scriptState["$cameraFirst"]=!e.scriptState["$cameraFirst"];
  bool first=cc?target->scriptState["$firstPerson"]!=0:(value(*c,"firstPerson")!=0)!=(e.scriptState["$cameraFirst"]!=0);float yaw=cc?target->scriptState["$yaw"]:-target->rotation.y*.01745329252f,pitch=cc?target->scriptState["$pitch"]:0;
  Vec3 eye=target->position+Vec3(0,value(*c,target->scriptState["$crouch"]?"crouchEyeHeight":"eyeHeight",1.62f),0),forward(sinf(yaw)*cosf(pitch),sinf(pitch),-cosf(yaw)*cosf(pitch));cameraTarget=eye+forward*(first?1:8);cameraPosition=eye;
  if(!first){Vec3 delta=forward*(-value(*c,"distance",3))+Vec3(cosf(yaw)*value(*c,"offsetX",.35f),.2f,sinf(yaw)*value(*c,"offsetX",.35f));float length=distance(delta,Vec3()),limit=length;if(length>.001f){for(const auto& wall:entities)if(&wall!=target&&wall.scene==activeScene&&wall.collider&&!wall.gravity)limit=std::min(limit,std::max(.15f,rayBox(eye,delta*(1/length),wall,length,.12f)-.1f));cameraPosition=eye+delta*(limit/length);cameraPosition.y=std::max(.2f,cameraPosition.y);}}
  if(value(*c,"hideTarget",1)){const Feature* health=feature(*target,"Health");target->visible=!first&&!(health&&value(*health,"hideOnDeath",0)&&target->health<=0);}
 }
 for(auto& e:entities)if(e.scene==activeScene){
  if(auto w=feature(e,"Weapon")){
   e.scriptState["$fire"]-=dt;float& reload=e.scriptState["$reload"];if(reload>0){reload=std::max(0.f,reload-dt);if(reload==0){e.scriptState["$ammo"]=value(*w,"magazine",24);emit(e,"ReloadComplete");}}
   if(input.square&&reload==0&&e.scriptState["$ammo"]<value(*w,"magazine",24)){reload=value(*w,"reloadTime",2);emit(e,"Reload");}
   if(input.fireHeld&&e.health>0&&reload==0&&e.scriptState["$fire"]<=0&&e.scriptState["$ammo"]>0){e.scriptState["$ammo"]--;e.scriptState["$fire"]=1/std::max(.01f,value(*w,"fireRate",6));emit(e,"Shot");Vec3 dir=cameraTarget+cameraPosition*(-1);float length=distance(dir,Vec3());if(length>.001f){dir=dir*(1/length);float nearest=value(*w,"range",40);Entity* hit=nullptr;for(auto& target:entities)if(&target!=&e&&target.scene==activeScene&&(target.collider||feature(target,"Health"))){float d=rayBox(cameraPosition,dir,target,nearest);if(d<nearest){nearest=d;hit=&target;}}if(hit){applyDamage(*hit,value(*w,"damage",20),e);emit(e,"Hit",value(*w,"damage",20),hit->id);}}}
  }
  for(const char* type:{"Trigger","Interactable"})if(auto c=feature(e,type)){
   Entity* target=findId(c->strings["target"]);if(!target)for(auto& candidate:entities)if(candidate.scene==activeScene&&feature(candidate,"CharacterController")){target=&candidate;break;}if(!target)continue;
   bool inside=distance(e.position,target->position)<=value(*c,"radius",2);if(std::string(type)=="Trigger"){if(inside&&!e.scriptState["$inside"]&&(!value(*c,"once")||!e.scriptState["$used"])){emit(e,c->strings["event"],1,target->id);emit(*target,c->strings["event"],1,e.id);e.scriptState["$used"]=1;}if(!inside&&e.scriptState["$inside"])emit(e,"TriggerExit",0,target->id);e.scriptState["$inside"]=inside;}
   else if(inside&&e.visible&&input.square){emit(e,c->strings["event"],1,target->id);emit(*target,c->strings["event"],1,e.id);if(value(*c,"hideOnUse"))e.visible=false;}
  }
 }
}
}
#endif
