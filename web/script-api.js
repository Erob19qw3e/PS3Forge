// Literal defaults only. This reads declarations; it never evaluates C++ code.
export function scriptFields(code){
 const clean=code.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g,''),fields=[],seen=new Set();
 const re=/\bself\.(number|flag)\(\s*"([A-Za-z][A-Za-z0-9 _-]{0,39})"\s*,\s*(true|false|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?f?)\s*\)/gi;
 for(const m of clean.matchAll(re)){
  const flag=m[1]==='flag',value=flag?m[3]==='true':Number(m[3].replace(/f$/i,''));
  if((flag&&!['true','false'].includes(m[3]))||(!flag&&!Number.isFinite(value))||seen.has(m[2]))continue;
  seen.add(m[2]);fields.push({name:m[2],type:flag?'flag':'number',value});
  if(fields.length===32)break;
 }return fields;
}

export function scriptSource(name,kind='rotate'){
 const bodies={
  blank:'    // Add your behavior here. self represents this object.',
  rotate:'    self.rotate(0, self.number("Spin speed", 60), 0);',
  move:'    self.moveByInput(self.number("Move speed", 3));\n    if (self.pressed(forge::Button::Jump))\n        self.jump(self.number("Jump strength", 5));',
  pickup:'    auto player = self.find("Player");\n    self.rotate(0, self.number("Spin speed", 60), 0);\n    if (self.collectBy(player, self.number("Pickup radius", 1.5)))\n        player.heal(self.number("Heal amount", 25));'
 };
 return '#include "Forge.h"\n\nFORGE_SCRIPT('+name+') {\n'+(bodies[kind]??bodies.blank)+'\n}\n';
}
