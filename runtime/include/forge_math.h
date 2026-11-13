#ifndef FORGE_MATH_H
#define FORGE_MATH_H
#include <cmath>
#include <algorithm>
namespace forgemath {
struct Matrix {
 float v[16];Matrix(){for(int i=0;i<16;i++)v[i]=(i%5==0)?1:0;}
 Matrix operator*(const Matrix& b)const{Matrix r;for(int i=0;i<4;i++)for(int j=0;j<4;j++){r.v[i*4+j]=0;for(int k=0;k<4;k++)r.v[i*4+j]+=v[i*4+k]*b.v[k*4+j];}return r;}
 void point(float x,float y,float z,float* out)const{for(int i=0;i<3;i++)out[i]=v[i*4]*x+v[i*4+1]*y+v[i*4+2]*z+v[i*4+3];}
 void normal(float x,float y,float z,float* out)const{
  float a=v[0],b=v[1],c=v[2],d=v[4],e=v[5],f=v[6],g=v[8],h=v[9],i=v[10];float det=a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g);
  if(fabsf(det)<1e-12f){out[0]=x;out[1]=y;out[2]=z;return;}
  out[0]=((e*i-f*h)*x+(f*g-d*i)*y+(d*h-e*g)*z)/det;out[1]=((c*h-b*i)*x+(a*i-c*g)*y+(b*g-a*h)*z)/det;out[2]=((b*f-c*e)*x+(c*d-a*f)*y+(a*e-b*d)*z)/det;
 }
};
inline Matrix trs(const float* t,const float* q,const float* s){
 float x=q[0],y=q[1],z=q[2],w=q[3];Matrix r;
 r.v[0]=(1-2*(y*y+z*z))*s[0];r.v[1]=2*(x*y-z*w)*s[1];r.v[2]=2*(x*z+y*w)*s[2];r.v[3]=t[0];
 r.v[4]=2*(x*y+z*w)*s[0];r.v[5]=(1-2*(x*x+z*z))*s[1];r.v[6]=2*(y*z-x*w)*s[2];r.v[7]=t[1];
 r.v[8]=2*(x*z-y*w)*s[0];r.v[9]=2*(y*z+x*w)*s[1];r.v[10]=(1-2*(x*x+y*y))*s[2];r.v[11]=t[2];return r;
}
inline Matrix euler(float x,float y,float z,float rx,float ry,float rz,float sx=1,float sy=1,float sz=1){
 float t[]={x,y,z},s[]={sx,sy,sz};rx*=.00872664626f;ry*=.00872664626f;rz*=.00872664626f;
 float a=sinf(rx),b=cosf(rx),c=sinf(ry),d=cosf(ry),e=sinf(rz),f=cosf(rz);float q[]={a*d*f+b*c*e,b*c*f-a*d*e,b*d*e+a*c*f,b*d*f-a*c*e};return trs(t,q,s);
}
inline void decompose(const Matrix& m,float* t,float* r,float* s){
 t[0]=m.v[3];t[1]=m.v[7];t[2]=m.v[11];for(int j=0;j<3;j++)s[j]=std::max(.0001f,sqrtf(m.v[j]*m.v[j]+m.v[4+j]*m.v[4+j]+m.v[8+j]*m.v[8+j]));
 float y=asinf(std::max(-1.f,std::min(1.f,m.v[2]/s[2]))),x,z;if(fabsf(cosf(y))>.0001f){x=atan2f(-m.v[6]/s[2],m.v[10]/s[2]);z=atan2f(-m.v[1]/s[1],m.v[0]/s[0]);}else{x=atan2f(m.v[9]/s[1],m.v[5]/s[1]);z=0;}
 r[0]=x*57.2957795f;r[1]=y*57.2957795f;r[2]=z*57.2957795f;
}
}
#endif
