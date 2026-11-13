const reserved=new Set(['main','forge','project','rsxutil','debugfont','debugfont_renderer','forge_generated']);
export function validScriptName(name){return typeof name==='string'&&/^[A-Za-z_][A-Za-z0-9_]{0,39}$/.test(name)&&!reserved.has(name.toLowerCase());}
export function suggestedCopyName(name,bank){
 const base=name.slice(0,34)+'Copy';let candidate=base,index=2;
 while(Object.hasOwn(bank,candidate))candidate=base.slice(0,34)+index++;
 return candidate;
}
export function duplicateSource(code,oldName,newName){
 if(!validScriptName(newName))throw Error('Use a script name with letters, numbers or underscores, up to 40 characters.');
 // Preserve comments, ordinary/raw strings and character literals. Rename C++
 // identifier tokens, including recursive calls and FORGE_SCRIPT entry names.
 const token=/R"([^ ()\\\t\r\n]{0,16})\([\s\S]*?\)\1"|\/\*[\s\S]*?\*\/|\/\/[^\n]*|"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'|[A-Za-z_]\w*/g;
 // Check real source with comments/strings blanked, retaining punctuation.
 const structural=code.replace(token,text=>/^[A-Za-z_]\w*$/.test(text)?text:' ');
 const escaped=oldName.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 if(!new RegExp('(?:FORGE_SCRIPT\\s*\\(\\s*'+escaped+'\\s*\\)|\\bvoid\\s+'+escaped+'\\s*\\([^;{}]*\\)\\s*\\{)').test(structural))
  throw Error('The entry function is defined in another script. Duplicate its defining script, or use Copy code.');
 return code.replace(token,text=>text===oldName?newName:text);
}
export function removeScript(project,name){
 delete project.scripts[name];let count=0;
 for(const scene of project.scenes)for(const entity of scene.entities){
  if(entity.script===name){entity.script='';count++;}
  if(entity.scripts){const before=entity.scripts.length;entity.scripts=entity.scripts.filter(item=>item.name!==name);count+=before-entity.scripts.length;}
  if(entity.scriptValues)delete entity.scriptValues[name];
 }return count;
}
