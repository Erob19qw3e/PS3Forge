#ifndef FORGE_SCRIPT_H
#define FORGE_SCRIPT_H
#include <stdio.h>
// Included by Forge.h; these helpers do not change the legacy script signature.
namespace forge {
enum class Button { Jump, Reload, Restart, Fire, Aim, Sprint };

class Object {
protected:
    Entity* object;
public:
    explicit Object(Entity* value=nullptr):object(value){}
    bool exists()const{return object!=nullptr;}
    bool visible()const{return object&&object->visible;}
    void show(){if(object)object->visible=true;}
    void hide(){if(object)object->visible=false;}
    Vec3 position()const{return object?object->position:Vec3();}
    void teleport(float x,float y,float z){if(object){object->position=Vec3(x,y,z);object->velocity=Vec3();}}
    float distanceTo(const Object& other)const{
        if(!object||!other.object)return 1e30f;
        Vec3 a=object->position,b=other.object->position;
        return sqrtf((a.x-b.x)*(a.x-b.x)+(a.y-b.y)*(a.y-b.y)+(a.z-b.z)*(a.z-b.z));
    }
    void play(const char* clip){if(object)object->play(clip);}
    float health()const{return object?object->health:0;}
    bool dead()const{return object&&object->health<=0;}
    void setHealth(float current,float maximum=100){
        if(object&&std::isfinite(current)&&std::isfinite(maximum)&&maximum>0){object->maxHealth=maximum;object->health=std::max(0.f,std::min(maximum,current));}
    }
    bool damage(float amount){if(!object||!std::isfinite(amount)||amount<=0||dead())return false;object->health=std::max(0.f,object->health-amount);return true;}
    void heal(float amount){if(object&&std::isfinite(amount)&&amount>0)object->health=std::min(object->maxHealth,object->health+amount);}
    bool collectBy(const Object& collector,float radius=1.5f){
        if(!visible()||!collector.exists()||radius<0||distanceTo(collector)>radius)return false;
        hide();return true;
    }
};

class ScriptContext:public Object {
    const Input& controls;
    std::string scope;
    unsigned down,pressedButtons;
    std::string key(const char* kind,const char* name)const{return scope+kind+name;}
public:
    const float deltaTime;
    ScriptContext(Entity& e,const Input& input,float dt,const char* script):Object(&e),controls(input),scope(std::string(script)+"."),down(0),pressedButtons(0),deltaTime(dt){
        if(input.crossHeld||input.cross)down|=1u<<unsigned(Button::Jump);
        if(input.square)down|=1u<<unsigned(Button::Reload);
        if(input.triangle)down|=1u<<unsigned(Button::Restart);
        if(input.fireHeld||input.r1)down|=1u<<unsigned(Button::Fire);
        if(input.aimHeld||input.l1)down|=1u<<unsigned(Button::Aim);
        if(input.sprint)down|=1u<<unsigned(Button::Sprint);
        float& previous=e.scriptState[key("@", "buttons")];
        pressedButtons=down&~unsigned(previous);
        // Face-button values already represent presses in the native input API.
        if(input.cross)pressedButtons|=1u<<unsigned(Button::Jump);
        if(input.square)pressedButtons|=1u<<unsigned(Button::Reload);
        if(input.triangle)pressedButtons|=1u<<unsigned(Button::Restart);
        previous=float(down);
    }
    bool firstFrame()const{return !object->started;}
    bool pressed(Button button)const{return (pressedButtons&(1u<<unsigned(button)))!=0;}
    bool held(Button button)const{return (down&(1u<<unsigned(button)))!=0;}
    Object find(const char* name)const{return Object(forge::find(name));}
    // Defaults are visible in the Inspector. Overrides belong to this object/script.
    float number(const char* name,float fallback)const{auto i=object->scriptValues.find(scope+name);return i==object->scriptValues.end()?fallback:i->second;}
    bool flag(const char* name,bool fallback)const{return number(name,fallback?1.f:0.f)!=0;}
    // Mutable per-object state is reset when the scene restarts.
    float& state(const char* name,float initial=0){auto result=object->scriptState.emplace(key("state.",name),initial);return result.first->second;}
    bool every(const char* name,float seconds){
        if(!std::isfinite(seconds)||seconds<=0)return false;
        float& elapsed=object->scriptState[key("timer.",name)];elapsed+=deltaTime;
        if(elapsed<seconds)return false;
        elapsed=fmodf(elapsed,seconds);return true;
    }
    void move(float x,float y,float z){object->position=object->position+Vec3(x,y,z)*deltaTime;}
    void rotate(float x,float y,float z){object->rotation=object->rotation+Vec3(x,y,z)*deltaTime;}
    void moveByInput(float speed){float x=controls.moveX,z=-controls.moveY,l=sqrtf(x*x+z*z);if(l>1){x/=l;z/=l;}move(x*speed,0,z*speed);}
    bool jump(float strength=5){if(!object->grounded||strength<=0)return false;object->velocity.y=strength;object->grounded=false;return true;}
    void lookAt(const Object& target){if(!target.exists())return;Vec3 p=target.position();object->rotation.y=atan2f(p.x-object->position.x,p.z-object->position.z)*57.29578f;}
    void moveToward(const Object& target,float speed,float stopDistance=0){
        if(!target.exists()||speed<=0)return;
        Vec3 p=target.position();float x=p.x-object->position.x,z=p.z-object->position.z,l=sqrtf(x*x+z*z);
        if(l<=std::max(0.f,stopDistance)||l<.00001f)return;
        float step=std::min(speed*deltaTime,l-std::max(0.f,stopDistance));object->position=object->position+Vec3(x/l*step,0,z/l*step);
    }
    void hud(const std::string& text){hudText=text;}
    void hud(const std::string& label,float value){char text[256];snprintf(text,sizeof(text),"%s: %.0f",label.c_str(),value);hudText=text;}
    void restartScene(){loadScene(activeScene);}
};
}

// Write FORGE_SCRIPT(MyItem) { ... } instead of the full C++ callback signature.
#define FORGE_SCRIPT(name) \
static void name##_update(forge::ScriptContext& self); \
void name(forge::Entity& entity,const forge::Input& input,float dt) { \
    forge::ScriptContext self(entity,input,dt,#name); name##_update(self); \
} \
static void name##_update(forge::ScriptContext& self)
#endif
