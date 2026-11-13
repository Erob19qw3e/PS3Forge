#ifndef FORGE_WORLD_COLLISION_H
#define FORGE_WORLD_COLLISION_H
#include <cmath>
#include <algorithm>
#include <initializer_list>
namespace forgeworld {
struct Point{float x,y,z;Point(float X=0,float Y=0,float Z=0):x(X),y(Y),z(Z){}Point operator+(Point b)const{return {x+b.x,y+b.y,z+b.z};}Point operator-(Point b)const{return {x-b.x,y-b.y,z-b.z};}Point operator*(float s)const{return {x*s,y*s,z*s};}};
struct Triangle{Point a,b,c;};
inline float dot(Point a,Point b){return a.x*b.x+a.y*b.y+a.z*b.z;}
inline Point cross(Point a,Point b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
inline float length2(Point a){return dot(a,a);}
inline float clamp01(float a){return std::max(0.f,std::min(1.f,a));}
inline Point closest(Point p,const Triangle&t){Point ab=t.b-t.a,ac=t.c-t.a,ap=p-t.a;float d1=dot(ab,ap),d2=dot(ac,ap);if(d1<=0&&d2<=0)return t.a;Point bp=p-t.b;float d3=dot(ab,bp),d4=dot(ac,bp);if(d3>=0&&d4<=d3)return t.b;float vc=d1*d4-d3*d2;if(vc<=0&&d1>=0&&d3<=0)return t.a+ab*(d1/(d1-d3));Point cp=p-t.c;float d5=dot(ab,cp),d6=dot(ac,cp);if(d6>=0&&d5<=d6)return t.c;float vb=d5*d2-d1*d6;if(vb<=0&&d2>=0&&d6<=0)return t.a+ac*(d2/(d2-d6));float va=d3*d6-d5*d4;if(va<=0&&(d4-d3)>=0&&(d5-d6)>=0)return t.b+(t.c-t.b)*((d4-d3)/((d4-d3)+(d5-d6)));float inv=1/(va+vb+vc);return t.a+ab*(vb*inv)+ac*(vc*inv);}
inline void segmentClosest(Point p1,Point q1,Point p2,Point q2,Point&c1,Point&c2){Point d1=q1-p1,d2=q2-p2,r=p1-p2;float a=dot(d1,d1),e=dot(d2,d2),f=dot(d2,r),s=0,t=0;if(a<1e-12f&&e<1e-12f){c1=p1;c2=p2;return;}if(a<1e-12f)t=clamp01(f/e);else{float c=dot(d1,r);if(e<1e-12f)s=clamp01(-c/a);else{float b=dot(d1,d2),den=a*e-b*b;if(den>1e-12f)s=clamp01((b*f-c*e)/den);t=(b*s+f)/e;if(t<0){t=0;s=clamp01(-c/a);}else if(t>1){t=1;s=clamp01((b-c)/a);}}}c1=p1+d1*s;c2=p2+d2*t;}
inline float rayTriangle(Point origin,Point direction,const Triangle&t,float limit){Point e1=t.b-t.a,e2=t.c-t.a,p=cross(direction,e2);float det=dot(e1,p);if(fabsf(det)<1e-8f)return limit+1;float inv=1/det;Point s=origin-t.a;float u=dot(s,p)*inv;if(u<0||u>1)return limit+1;Point q=cross(s,e1);float v=dot(direction,q)*inv;if(v<0||u+v>1)return limit+1;float at=dot(e2,q)*inv;return at>=0&&at<=limit?at:limit+1;}
inline bool capsuleContact(Point center,Point previous,float radius,float halfHeight,const Triangle&t,Point&normal,float&penetration){ 
 // Reject triangles outside the capsule AABB before segment/triangle distance work.
 const float vertical=std::max(radius,halfHeight);
 if(std::min({t.a.x,t.b.x,t.c.x})>center.x+radius || std::max({t.a.x,t.b.x,t.c.x})<center.x-radius ||
    std::min({t.a.z,t.b.z,t.c.z})>center.z+radius || std::max({t.a.z,t.b.z,t.c.z})<center.z-radius ||
    std::min({t.a.y,t.b.y,t.c.y})>center.y+vertical || std::max({t.a.y,t.b.y,t.c.y})<center.y-vertical)
  return false;
 Point n=cross(t.b-t.a,t.c-t.a);float nn=length2(n);if(nn<1e-12f)return false;n=n*(1/sqrtf(nn));float stem=std::max(0.f,halfHeight-radius);Point low=center+Point(0,-stem,0),high=center+Point(0,stem,0),onCapsule,onTriangle;float best=1e30f;
 float hit=rayTriangle(low,high-low,t,1);if(hit<=1){onCapsule=low+(high-low)*hit;onTriangle=onCapsule;best=0;}else{for(Point p:{low,high}){Point q=closest(p,t);float d=length2(p-q);if(d<best){best=d;onCapsule=p;onTriangle=q;}}Point edges[]={t.a,t.b,t.c,t.a};for(int i=0;i<3;i++){Point p,q;segmentClosest(low,high,edges[i],edges[i+1],p,q);float d=length2(p-q);if(d<best){best=d;onCapsule=p;onTriangle=q;}}}
 if(best>=radius*radius)return false;float distance=sqrtf(std::max(0.f,best));normal=distance>1e-6f?(onCapsule-onTriangle)*(1/distance):(dot(previous-t.a,n)>=0?n:n*(-1));penetration=radius-distance;return true;}
}
#endif
