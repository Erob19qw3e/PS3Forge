#ifndef IRON_COMBAT_H
#define IRON_COMBAT_H
#include <cmath>
#include <algorithm>
namespace iron {
const float PI=3.14159265359f;
inline float clamp(float x,float a,float b){return std::max(a,std::min(b,x));}
struct V {float x,z; V(float a=0,float b=0):x(a),z(b){} V operator+(V b)const{return V(x+b.x,z+b.z);} V operator-(V b)const{return V(x-b.x,z-b.z);} V operator*(float f)const{return V(x*f,z*f);} };
inline float dot(V a,V b){return a.x*b.x+a.z*b.z;}
inline float length(V a){return std::sqrt(dot(a,a));}
inline V forward(float yaw){return V(std::sin(yaw),-std::cos(yaw));}
inline float wrap(float a){while(a>PI)a-=2*PI;while(a<-PI)a+=2*PI;return a;}
inline float segmentDistance(V p,V a,V b){V d=b-a;float q=dot(d,d);float t=q>0.00001f?clamp(dot(p-a,d)/q,0,1):0;return length(p-(a+d*t));}
struct Fighter {
 V pos,vel;float yaw,hp,stamina,swing,cooldown,dodge,flash,fall,walk;bool blocking,hit;int side;
 Fighter():pos(),vel(),yaw(0),hp(100),stamina(100),swing(-1),cooldown(0),dodge(0),flash(0),fall(0),walk(0),blocking(false),hit(false),side(1){}
};
struct Input {float right,forward,yaw; bool attack,block,dodge;int side; Input():right(0),forward(0),yaw(0),attack(false),block(false),dodge(false),side(1){} };
struct Game {
 Fighter player,enemy;int wins;float wait,clock,aiTimer,messageTime;bool victory;int event;
 Game(){reset();}
 void reset(){player=Fighter();enemy=Fighter();player.pos=V(0,3);enemy.pos=V(0,-3);enemy.yaw=PI;wins=0;wait=0;clock=0;aiTimer=1.4f;messageTime=0;victory=false;event=0;}
 static float bladeAngle(const Fighter& f){return f.yaw+(f.swing<0?0.65f:((f.swing/.64f)*2.8f-1.4f)*f.side);}
 static V hand(const Fighter& f){return f.pos+forward(f.yaw)*.4f;}
 static V tip(const Fighter& f,float time){return hand(f)+forward(f.yaw+((time/.64f)*2.8f-1.4f)*f.side)*1.65f;}
 static bool begin(Fighter& f,int side){if(f.hp<=0||f.swing>=0||f.cooldown>0||f.stamina<24||f.dodge>0)return false;f.swing=0;f.stamina-=24;f.hit=false;f.side=side<0?-1:1;f.blocking=false;return true;}
 void strike(Fighter& a,Fighter& b,float previous,float next){
  if(a.hp<=0||b.hp<=0||a.hit||previous<0||b.dodge>0.28f)return;
  bool contact=false;
  for(int i=0;i<=4;i++) {float t=previous+(next-previous)*(i/4.f);if(t<.10f||t>.54f)continue;if(segmentDistance(b.pos,hand(a),tip(a,t))<.46f)contact=true;}
  if(!contact)return;
  a.hit=true;V toward=a.pos-b.pos;float dist=length(toward);bool facing=dist>.001f&&dot(forward(b.yaw),toward*(1/dist))>.25f;
  if(b.blocking&&facing&&b.stamina>=18){b.stamina-=18;b.vel=b.vel+forward(a.yaw)*1.5f;event=2;}
  else {b.hp=std::max(0.f,b.hp-34.f);b.flash=.22f;b.vel=b.vel+forward(a.yaw)*4.f;event=1;}
  messageTime=.4f;
 }
 static void advance(Fighter& f,float dt){
  f.cooldown=std::max(0.f,f.cooldown-dt);f.dodge=std::max(0.f,f.dodge-dt);f.flash=std::max(0.f,f.flash-dt);
  if(f.hp<=0){f.blocking=false;f.fall=std::min(1.f,f.fall+dt);}
  else {f.stamina=std::min(100.f,f.stamina+dt*(f.blocking?4.f:19.f));if(f.swing>=0){f.swing+=dt;if(f.swing>.64f){f.swing=-1;f.cooldown=.20f;}}}
  f.pos=f.pos+f.vel*dt;f.vel=f.vel*std::exp(-7.f*dt);f.pos.x=clamp(f.pos.x,-8.8f,8.8f);f.pos.z=clamp(f.pos.z,-8.8f,8.8f);
 }
 void step(const Input& in,float dt){
  clock+=dt;messageTime=std::max(0.f,messageTime-dt);
  if(victory||player.hp<=0){advance(player,dt);advance(enemy,dt);return;}
  if(enemy.hp<=0){
   advance(enemy,dt);advance(player,dt);wait+=dt;
   if(wait>2){wins++;if(wins>=5){victory=true;return;}enemy=Fighter();enemy.pos=V(player.pos.x>0?-5.f:5.f,-5);enemy.yaw=PI;enemy.hp=100;player.hp=std::min(100.f,player.hp+20);player.stamina=100;wait=0;aiTimer=1.3f;}
   return;
  }
  player.yaw=in.yaw;
  player.blocking=in.block&&player.swing<0&&player.dodge<=0&&player.stamina>2;
  float mag=std::sqrt(in.right*in.right+in.forward*in.forward);float n=mag>1?1/mag:1;
  V move=(V(std::cos(in.yaw),std::sin(in.yaw))*in.right+forward(in.yaw)*in.forward)*n;
  if(in.dodge&&player.stamina>=30&&player.dodge<=0&&player.swing<0){player.stamina-=30;player.dodge=.60f;player.vel=move*(length(move)>.1f?11.f:0.f);if(length(move)<.1f)player.vel=forward(player.yaw)*-10.f;}
  if(in.attack)begin(player,in.side);
  float speed=player.blocking?1.5f:(player.swing>=0?1.8f:3.4f);
  player.pos=player.pos+move*(speed*dt);player.walk+=length(move)*dt*9;
  V delta=player.pos-enemy.pos;float distance=length(delta);enemy.yaw=std::atan2(delta.x,-delta.z);
  enemy.blocking=player.swing>=0&&enemy.swing<0&&enemy.stamina>22&&((wins%2)==1);
  if(distance>2.05f&&enemy.swing<0) {enemy.pos=enemy.pos+forward(enemy.yaw)*dt*(1.8f+.13f*wins);enemy.walk+=dt*7;}
  aiTimer-=dt;if(distance<2.5f&&aiTimer<=0){if(begin(enemy,(wins%2)?-1:1))aiTimer=1.6f-.1f*wins;}
  float pa=player.swing,ea=enemy.swing;
  advance(player,dt);advance(enemy,dt);
  if(pa>=0)strike(player,enemy,pa,pa+dt);
  if(ea>=0)strike(enemy,player,ea,ea+dt);
  V sep=enemy.pos-player.pos;float d=length(sep);if(d<.9f){V normal=d>.001f?sep*(1/d):V(1,0);float push=(.9f-d)*.5f;player.pos=player.pos-normal*push;enemy.pos=enemy.pos+normal*push;}
  player.pos.x=clamp(player.pos.x,-8.8f,8.8f);player.pos.z=clamp(player.pos.z,-8.8f,8.8f);enemy.pos.x=clamp(enemy.pos.x,-8.8f,8.8f);enemy.pos.z=clamp(enemy.pos.z,-8.8f,8.8f);
 }
};
}
#endif
