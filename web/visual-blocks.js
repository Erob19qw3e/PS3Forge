const marker = '// PS3Forge Visual Blocks v1 ';
const buttons = {Jump:'Cross', Reload:'Square', Restart:'Triangle', Fire:'R2', Aim:'L2', Sprint:'L3'};
const number = (name, value, min = -10000, max = 10000) => ({name, value, min, max});
const word = (name, value) => ({name, value});
const events = {
    start: ['When the scene starts', [], () => 'self.firstFrame()'],
    update: ['Every frame', [], () => 'true'],
    press: ['When a button is pressed', [{name:'Button', value:'Jump', options:buttons}],
        ([button]) => 'self.pressed(forge::Button::' + button + ')'],
    timer: ['Every few seconds', [number('Seconds', 1, 0.05, 3600)],
        ([seconds], index) => 'self.every("Block timer ' + index + '", ' + seconds + ')']
};
const actions = {
    move: ['Move', [number('X', 1), number('Y', 0), number('Z', 0)], args => 'self.move(' + args.join(', ') + ');'],
    rotate: ['Rotate', [number('X', 0), number('Y', 60), number('Z', 0)], args => 'self.rotate(' + args.join(', ') + ');'],
    stick: ['Move with left stick', [number('Speed', 4, 0)], ([speed]) => 'self.moveByInput(' + speed + ');'],
    jump: ['Jump', [number('Strength', 5, 0)], ([strength]) => 'self.jump(' + strength + ');'],
    show: ['Show object', [], () => 'self.show();'],
    hide: ['Hide object', [], () => 'self.hide();'],
    play: ['Play animation', [word('Clip', 'Idle')], ([clip]) => 'self.play(' + clip + ');'],
    hud: ['Show text', [word('Text', 'Hello!')], ([message]) => 'self.hud(' + message + ');'],
    heal: ['Heal object', [number('Amount', 25, 0)], ([amount]) => 'self.heal(' + amount + ');'],
    restart: ['Restart scene', [], () => 'self.restartScene(); return;']
};

function defaults(definition) {
    return definition[1].map(field => field.value);
}

function callArgs(definition, values) {
    if (!Array.isArray(values) || values.length !== definition[1].length) throw Error('Invalid block fields.');
    return definition[1].map((field, index) => {
        const value = values[index];
        if (field.options) {
            if (!Object.hasOwn(field.options, value)) throw Error('Choose a valid option for ' + field.name + '.');
            return value;
        }
        if (typeof field.value === 'number') {
            if (typeof value !== 'number' || !Number.isFinite(value) || value < field.min || value > field.max)
                throw Error(field.name + ' must be between ' + field.min + ' and ' + field.max + '.');
            return String(value);
        }
        if (typeof value !== 'string' || !value.trim() || value.length > 100 || /[\x00-\x1f\x7f]/.test(value))
            throw Error(field.name + ' must contain 1–100 characters on one line.');
        return JSON.stringify(value);
    });
}

const comparisons = {lt:'<', le:'<=', eq:'==', ne:'!=', ge:'>=', gt:'>'};
const logic = {and:'AND', or:'OR', xor:'XOR', nand:'NAND', nor:'NOR', xnor:'XNOR'};
const mathOps = {add:'+', sub:'-', mul:'*', div:'/'};
const choice = (name,value,options) => ({name,value,options});
const testFields = suffix => [word('Variable'+suffix,'Score'), choice('Operator'+suffix,'ge',comparisons),
    number('Value'+suffix,10)];
const comparison = ([key,op,value]) => 'self.state(' + key + ') ' + comparisons[op] + ' ' + value;
const control = {
    ifCompare: ['If variable', testFields(''), comparison],
    ifElse: ['If / Else', testFields(''), comparison],
    ifNot: ['If NOT', testFields(''), args => '!(' + comparison(args) + ')'],
    ifLogic: ['If two comparisons', [...testFields(' A'),choice('Logic','and',logic),...testFields(' B')],
        args => {
            const a = '(' + comparison(args.slice(0,3)) + ')';
            const b = '(' + comparison(args.slice(4)) + ')';
            const gate = args[3];
            const op = {and:'&&',or:'||',xor:'!=',nand:'&&',nor:'||',xnor:'=='}[gate];
            const expression = '(' + a + ' ' + op + ' ' + b + ')';
            return gate === 'nand' || gate === 'nor' ? '!' + expression : expression;
        }],
    ifBoolean: ['If true or false', [choice('Value','true',{true:'True',false:'False'})], ([value]) => value],
    repeat: ['Repeat', [number('Times',3,1,100)], ([times]) => times]
};
const playerActions = {
    playerMove: ['Move with left stick (classic)', [number('Speed',3.5,0)],
        ([speed]) => 'self.move(input.moveX * ' + speed + ', 0, -input.moveY * ' + speed + ');'],
    playerTurn: ['Turn with right stick', [number('Degrees per second',120)],
        ([speed]) => 'self.rotate(0, input.lookX * ' + speed + ', 0);'],
    playerAnimation: ['Walk / idle animation', [word('Walk clip','Walk'),word('Idle clip','Idle'),number('Dead zone',0.1,0,2)],
        ([walk,idle,threshold]) => 'self.play(fabsf(input.moveX) + fabsf(input.moveY) > static_cast<float>(' + threshold + ') ? ' + walk + ' : ' + idle + ');'],
    playerJump: ['Jump with Cross (classic)', [number('Strength',5.5,0)],
        ([strength]) => 'if (input.cross && entity.grounded) entity.velocity.y = ' + strength + ';']
};
Object.assign(actions, playerActions);

const legacySources = {"Spin": "#include \"Forge.h\"\nvoid Spin(forge::Entity& e, const forge::Input&, float dt) {\n    e.rotation.y += 45.0f * dt;\n}", "Player": "#include \"Forge.h\"\nvoid Player(forge::Entity& e, const forge::Input& input, float dt) {\n    e.position.x += input.moveX * 3.5f * dt;\n    e.position.z -= input.moveY * 3.5f * dt;\n    e.rotation.y += input.lookX * 120.0f * dt;\n    bool moving = fabsf(input.moveX) + fabsf(input.moveY) > 0.1f;\n    e.play(moving ? \"Walk\" : \"Idle\");\n    if (input.cross && e.grounded) e.velocity.y = 5.5f;\n}"};
export function isConvertibleScript(name,source) {
    return Object.hasOwn(legacySources,name) &&
        source.replace(/\r\n/g,'\n').trim() === legacySources[name];
}
export function visualSourceForScript(name,source) {
    if (!isConvertibleScript(name,source)) return source;
    const steps = name === 'Spin' ? [{type:'rotate',values:[0,45,0]}] :
        Object.entries(playerActions).map(([type,definition]) => ({type,values:defaults(definition)}));
    return compileBlocks(name,[{type:'update',values:[],steps}]);
}

const isControl = type => Object.hasOwn(control,type);

function emitSteps(lines, steps, depth, budget) {
    if (!Array.isArray(steps) || !steps.length || steps.length > 24)
        throw Error('Each event or branch needs 1-24 blocks.');
    if (depth > 5) throw Error('Nest up to four control blocks.');
    const indent = '    '.repeat(depth + 1);
    for (const step of steps) {
        if (--budget.left < 0) throw Error('Use up to 288 blocks per script.');
        if (!isControl(step.type)) {
            if (!Object.hasOwn(actions,step.type)) throw Error('Unknown action.');
            const action = actions[step.type];
            if (Object.hasOwn(playerActions,step.type) || step.type === 'sendEvent') budget.rawInput = true;
            lines.push(indent + action[2](callArgs(action,step.values)));
            continue;
        }
        const definition = control[step.type];
        const args = callArgs(definition,step.values);
        const expression = definition[2](args);
        if (step.type === 'repeat' && !Number.isInteger(step.values[0])) throw Error('Times must be a whole number.');
        const guard = 'if (++blockOperations > 1024) return;';
        const opening = step.type === 'repeat'
            ? 'for (int blockRepeat = 0; blockRepeat < ' + expression + '; ++blockRepeat) {'
            : 'if (' + expression + ') {';
        lines.push(indent + opening);
        if (step.type === 'repeat') lines.push(indent + '    ' + guard);
        emitSteps(lines,step.then,depth+1,budget);
        if (step.type === 'ifElse') {
            lines.push(indent + '} else {');
            emitSteps(lines,step.otherwise,depth+1,budget);
        }
        lines.push(indent + '}');
    }
}

export function compileBlocks(name, rules) {
    if (!/^[A-Za-z_][A-Za-z0-9_]{0,39}$/.test(name)) throw Error('Invalid script name.');
    if (!Array.isArray(rules) || !rules.length || rules.length > 12) throw Error('Add between 1 and 12 events.');
    const lines = ['#include "Forge.h"', '', 'FORGE_SCRIPT(' + name + ') {'];
    const hasRepeat = steps => Array.isArray(steps) && steps.some(step => step.type === 'repeat' ||
        (isControl(step.type) && (hasRepeat(step.then) || hasRepeat(step.otherwise))));
    const budget = {left:288};
    rules.forEach(({type, values, steps}, index) => {
        if (!Object.hasOwn(events, type)) throw Error('Unknown event.');
        if (!Array.isArray(steps) || !steps.length || steps.length > 24) throw Error('Each event needs 1–24 actions.');
        const event = events[type];
        lines.push('    if (' + event[2](callArgs(event, values), index + 1) + ') {');
        if (type === 'receiveEvent') budget.rawInput = true;
        emitSteps(lines,steps,1,budget);
        lines.push('    }');
    });
    if (rules.some(rule => hasRepeat(rule.steps))) lines.splice(3,0,'    int blockOperations = 0;');
    if (budget.rawInput) {
        lines[2] = 'void ' + name + '(forge::Entity& entity, const forge::Input& input, float dt) {';
        lines.splice(3,0,'    forge::ScriptContext self(entity,input,dt,"' + name + '");');
    }
    lines.push('}', '');
    const source = marker + encodeURIComponent(JSON.stringify(rules)) + '\n' + lines.join('\n');
    if (source.length > 100000) throw Error('The script is too large. Shorten some text or split it into two scripts.');
    return source;
}

export function readBlocks(name, source) {
    const normalized = source.replace(/\r\n/g, '\n').trimEnd();
    if (!normalized.startsWith(marker)) return null;
    const rules = JSON.parse(decodeURIComponent(normalized.slice(marker.length, normalized.indexOf('\n'))));
    if (compileBlocks(name, rules).trimEnd() !== normalized)
        throw Error('This script was edited in C++. Open it in C++ Script to keep those changes.');
    return rules;
}

function node(tag, text) {
    const item = document.createElement(tag);
    if (text) item.textContent = text;
    return item;
}

function button(label, handler) {
    const item = node('button', label);
    item.type = 'button';
    item.onclick = handler;
    return item;
}

function select(entries) {
    const item = node('select');
    for (const [value, label] of entries) {
        const option = node('option', label);
        option.value = value;
        item.append(option);
    }
    return item;
}

function fields(definition, values) {
    return definition[1].map((field, index) => {
        const label = node('label', field.name + ' ');
        const input = field.options ? select(Object.entries(field.options)) : node('input');
        if (typeof field.value === 'number') {
            input.type = 'number';
            input.step = 'any';
            input.min = field.min;
            input.max = field.max;
        } else if (!field.options) {
            input.type = 'text';
            input.maxLength = 100;
        }
        input.value = values[index] ?? '';
        input.oninput = () => {
            values[index] = input.type === 'number' ? input.valueAsNumber : input.value;
        };
        label.append(input);
        return label;
    });
}

const toolboxStyles = "\n.forge-toolbox[open]{display:grid;grid-template-rows:auto minmax(0,1fr) auto;width:min(1420px,97vw);height:92vh;max-height:92vh;padding:0;overflow:hidden;border-radius:8px;background:#25272a;color:#edf0f2;font:13px 'Segoe UI',sans-serif}\n.forge-toolbox>header{height:auto;min-height:56px;display:flex;flex-wrap:wrap;gap:10px;padding:10px 16px;background:#303237;border-bottom:1px solid #494b51}\n.forge-toolbox h2{margin:0 auto 0 0;font-size:18px;font-weight:600}\n.forge-toolbox button:focus-visible{outline:2px solid #d5e7fa;outline-offset:2px}\n.forge-toolbox .forge-apply{background:#dce8f2;color:#192530;font-weight:600}\n.forge-block-body{display:grid;grid-template-columns:230px minmax(0,1fr);min-height:0}\n.forge-toolbox .forge-block-sidebar{display:flex;flex-direction:column;gap:10px;overflow:auto;padding:12px;background:#282a2d;border-right:1px solid #484a50}\n.forge-block-sidebar input[type=search]{width:100%;padding:7px 9px;background:#1d1f22;border-color:#53575e}\n.forge-categories{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px}\n.forge-categories button{text-align:left;background:#303238;border-color:transparent}\n.forge-categories button:hover,.forge-categories button[aria-pressed=true]{background:#444851;border-color:#686f7a;color:white}\n.forge-palette{display:grid;gap:6px}\n.forge-toolbox [data-color]{--block-accent:#adc0e2}\n.forge-toolbox [data-color=\"0\"]{--block-accent:#d7b17b}\n.forge-toolbox [data-color=\"1\"]{--block-accent:#8dbce8}\n.forge-toolbox [data-color=\"2\"]{--block-accent:#a8c9b2}\n.forge-toolbox [data-color=\"3\"]{--block-accent:#c6b4e9}\n.forge-toolbox [data-color=\"4\"]{--block-accent:#dfaaa7}\n.forge-toolbox [data-color=\"5\"]{--block-accent:#8fc9c7}\n.forge-toolbox [data-color=\"6\"]{--block-accent:#c6c894}\n.forge-toolbox .forge-palette-block,.forge-toolbox .event-block,.forge-toolbox .action-block{border:1px solid #535760;border-left:4px solid var(--block-accent);background:#393d44;border-radius:5px}\n.forge-toolbox .forge-palette-block{text-align:left;padding:6px 8px;white-space:normal;cursor:grab}\n.forge-toolbox .forge-palette-block:hover{background:#4c525d}\n.forge-toolbox .forge-workspace{overflow:auto;padding:16px 18px;background:#24262a radial-gradient(#444750 1px,transparent 1px) 0 0/18px 18px}\n.forge-workspace h3{margin:0;font-size:14px}\n.forge-toolbox .forge-workspace section{background:#2c2f35;border-color:#50545d}\n.forge-toolbox .forge-workspace .selected-event{border-color:#aabdd0}\n.forge-toolbox .event-block{background:#4a4139}\n.forge-toolbox .forge-event-select{font-weight:600;background:#302b27}\n.forge-toolbox .action-block{margin-left:14px}\n.forge-toolbox .forge-action-drop{margin:7px 0 0 14px;padding:7px;border:1px dashed #737982;border-radius:4px;color:#cbd0d6}\n.forge-toolbox .forge-block-message{height:auto;min-height:35px;padding:6px 14px;font-size:12px;color:#d1d5db;background:#303237}\n@media(max-width:680px){.forge-block-body{grid-template-columns:155px minmax(0,1fr)}.forge-categories{grid-template-columns:1fr}.forge-toolbox .forge-workspace{padding:10px}}\n";

const sections = {
    Events: ['start', 'update', 'press', 'timer', 'held', 'nearby', 'collect', 'lowHealth', 'defeated', 'variableAtLeast', 'receiveEvent'],
    Movement: ['move', 'rotate', 'stick', 'jump', 'teleport', 'follow', 'face', 'teleportTarget'],
    Objects: ['show', 'hide', 'showTarget', 'hideTarget'],
    Animation: ['play', 'playTarget'],
    Health: ['heal', 'damage', 'health', 'healTarget'],
    HUD: ['hud', 'showHealth'],
    Scene: ['restart'], Variables: ['setVariable', 'addVariable', 'showVariable', 'copyVariable'],
    'Flow control': ['repeat'], Logic: ['ifCompare','ifElse','ifNot','ifLogic','ifBoolean'],
    Math: ['calculate','clampVariable'], Player: Object.keys(playerActions), Signals: ['sendEvent']
};
Object.assign(events, {
    held: ['While a button is held', [{name:'Button', value:'Jump', options:{Jump:'Cross', Fire:'R2', Aim:'L2', Sprint:'L3'}}],
        ([key]) => 'self.held(forge::Button::' + key + ')']
});
Object.assign(actions, {
    teleport: ['Teleport', [number('X',0), number('Y',1), number('Z',0)], args => 'self.teleport(' + args.join(', ') + ');'],
    follow: ['Move toward object', [word('Object','Player'), number('Speed',3,0), number('Stop distance',1,0)],
        ([target,speed,distance]) => 'self.moveToward(self.find(' + target + '), ' + speed + ', ' + distance + ');'],
    face: ['Face object', [word('Object','Player')], ([target]) => 'self.lookAt(self.find(' + target + '));'],
    damage: ['Damage object', [number('Amount',10,0)], ([amount]) => 'self.damage(' + amount + ');'],
    health: ['Set health', [number('Current',100,0), number('Maximum',100,1)], args => 'self.setHealth(' + args.join(', ') + ');'],
    showHealth: ['Show health', [word('Label','Health')], ([label]) => 'self.hud(' + label + ', self.health());']
});
Object.assign(events, {
    nearby: ['While near an object', [word('Object','Player'), number('Radius',2,0)],
        ([target,radius]) => 'self.find(' + target + ').exists() && self.distanceTo(self.find(' + target + ')) <= ' + radius],
    collect: ['When picked up', [word('Collector','Player'), number('Radius',1.5,0)],
        ([target,radius]) => 'self.collectBy(self.find(' + target + '), ' + radius + ')'],
    lowHealth: ['While health is below', [number('Health',25,0)],
        ([health]) => 'self.health() < ' + health],
    defeated: ['When health reaches zero', [], (_, index) =>
        'self.dead() && self.state("Block defeated ' + index + '") == 0 && (self.state("Block defeated ' + index + '") = 1)'],
    variableAtLeast: ['While a variable is at least', [word('Variable','Score'), number('Value',10)],
        ([key,value]) => 'self.state(' + key + ') >= ' + value]
});
Object.assign(actions, {
    setVariable: ['Set variable', [word('Variable','Score'), number('Value',0)],
        ([key,value]) => 'self.state(' + key + ') = ' + value + ';'],
    addVariable: ['Change variable by', [word('Variable','Score'), number('Amount',1)],
        ([key,value]) => 'self.state(' + key + ') += ' + value + ';'],
    showVariable: ['Show variable', [word('Label','Score'), word('Variable','Score')],
        ([label,key]) => 'self.hud(' + label + ', self.state(' + key + '));'],
    showTarget: ['Show another object', [word('Object','Door')], ([target]) => 'self.find(' + target + ').show();'],
    hideTarget: ['Hide another object', [word('Object','Door')], ([target]) => 'self.find(' + target + ').hide();'],
    healTarget: ['Heal another object', [word('Object','Player'), number('Amount',25,0)],
        ([target,amount]) => 'self.find(' + target + ').heal(' + amount + ');'],
    playTarget: ['Play animation on another object', [word('Object','Door'), word('Clip','Open')],
        ([target,clip]) => 'self.find(' + target + ').play(' + clip + ');'],
    teleportTarget: ['Teleport another object', [word('Object','Player'), number('X',0), number('Y',1), number('Z',0)],
        ([target,...coords]) => 'self.find(' + target + ').teleport(' + coords.join(', ') + ');']
});
Object.assign(actions, {
    copyVariable: ['Copy variable', [word('To','Score'),word('From','Bonus')],
        ([to,from]) => 'self.state(' + to + ') = self.state(' + from + ');'],
    calculate: ['Calculate with a variable', [word('Variable','Score'),choice('Operator','add',mathOps),number('Value',2)],
        ([key,op,value]) => {
            if (op === 'div' && Number(value) === 0) throw Error('Division by zero.');
            return 'self.state(' + key + ') ' + mathOps[op] + '= ' + value + ';';
        }],
    clampVariable: ['Clamp variable', [word('Variable','Score'),number('Minimum',0),number('Maximum',100)],
        ([key,min,max]) => {
            if (Number(min) > Number(max)) throw Error('Minimum must be at most Maximum.');
            return 'self.state(' + key + ') = std::max(static_cast<float>(' + min + '), std::min(static_cast<float>(' + max + '), self.state(' + key + ')));';
        }]
});
events.receiveEvent = ['When event received', [word('Event','OpenDoor')],
    ([event]) => 'forge::pollEvent(entity, ' + event + ')'];
actions.sendEvent = ['Send event to object', [word('Object','Door'),word('Event','OpenDoor')],
    ([target,event]) => 'if (auto* receiver = forge::find(' + target + ')) forge::emit(*receiver, ' + event + ');'];

const blockHelp = {
    receiveEvent:'Consumes one matching event from this object. Use the event name configured on a Trigger or in Send event.',
    sendEvent:'Sends an event to a named object in the active scene.', 
    ifCompare:'Drop actions in Then. Compare a variable with a number.',
    ifElse:'Drop one set of actions in Then and another in Else.',
    ifNot:'Runs Then when the comparison is false.',
    ifLogic:'Combine two comparisons with a logic gate.',
    repeat:'Runs the blocks inside the loop a fixed number of times.',
    nearby:'Runs every frame while the named object is in range.',
    collect:'Hides this object and runs once per pickup. Showing the object again allows another pickup.',
    lowHealth:'Runs every frame while health is below the threshold.',
    defeated:'Runs once per scene, the first time this object has zero health.',
    variableAtLeast:'Runs every frame while the variable is at or above this value.',
    setVariable:'Variables belong to this object and script. They reset with the scene.',
    addVariable:'Use a negative amount to subtract. A new variable starts at zero.',
    showVariable:'Displays this object and script variable in the HUD.'
};
const keywords = {start:'on start inizio', update:'tick aggiornamento', press:'controller tasto pulsante',
    held:'controller tasto pulsante', timer:'time wait tempo secondi', move:'sposta cammina',
    rotate:'ruota rotazione', stick:'controller joystick movimento', jump:'salta salto',
    teleport:'position posizione teletrasporto', play:'clip animazione', heal:'cura vita',
    health:'hp vita salute', damage:'danno hp', hud:'message text messaggio testo', restart:'reset riavvia'};
const catalogue = Object.entries(sections).flatMap(([category, keys], index) =>
    keys.map(type => ({category,index,type,definition:(events[type] || control[type] || actions[type])})));
const entryByType = Object.fromEntries(catalogue.map(entry => [entry.type, entry]));

export function searchBlocks(query, category = 'All blocks') {
    const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
    return catalogue.filter(entry => {
        if (!terms.length) return category === 'All blocks' || category === entry.category;
        const [label, parameters] = entry.definition;
        const options = parameters.flatMap(field => Object.values(field.options || {}));
        const words = [label, entry.category, ...parameters.map(field => field.name), ...options, keywords[entry.type] || '', isControl(entry.type) ? 'se confronto condizione ' + (entry.type === 'repeat' ? 'ripeti ciclo' : '') : '', {
            nearby:'vicino distanza', collect:'raccogli moneta pickup', lowHealth:'vita salute',
            defeated:'sconfitta morte vita', variableAtLeast:'condizione punteggio score',
            setVariable:'imposta variabile punteggio', addVariable:'aumenta somma variabile punteggio',
            showVariable:'mostra variabile punteggio', showTarget:'mostra oggetto',
            hideTarget:'nascondi oggetto', healTarget:'cura giocatore', playTarget:'animazione',
            teleportTarget:'teletrasporto'
        }[entry.type] || ''].join(' ').toLowerCase();
        return terms.every(term => words.includes(term));
    });
}

export function openBlocks({name, source, apply}) {
    const rules = source ? readBlocks(name, source) : [
        {type:'update', values:[], steps:[{type:'rotate', values:defaults(actions.rotate)}]}
    ];
    if (!rules) throw Error('Choose New visual script to create a block script.');
    const dialog = node('dialog');
    dialog.className = 'forge-blocks forge-toolbox';
    dialog.setAttribute('aria-labelledby', 'forge-blocks-title');
    const title = node('h2', 'Visual Blocks');
    title.id = 'forge-blocks-title';
    const nameInput = node('input');
    nameInput.maxLength = 40;
    nameInput.value = name;
    nameInput.readOnly = Boolean(source);
    const nameLabel = node('label', 'Script name ');
    nameLabel.append(nameInput);
    const header = node('header');
    header.append(title, nameLabel, button('Cancel', () => dialog.close()), button('Apply blocks', () => {
        try {
            const scriptName = nameInput.value.trim();
            apply(scriptName, compileBlocks(scriptName, rules));
            dialog.close();
        } catch (problem) {
            message.textContent = problem.message;
        }
    }));
    header.lastChild.className = 'forge-apply';

    const style = node('style');
    style.textContent = toolboxStyles + `
        .forge-toolbox[open]{border-radius:0;background:#222325;border:1px solid #44464a}
        .forge-toolbox>header,.forge-toolbox .forge-block-message{background:#2c2d30}
        .forge-toolbox .forge-block-sidebar{background:#262729}
        .forge-toolbox .forge-workspace{background:#1e2022 radial-gradient(#35373a 1px,transparent 1px) 0 0/18px 18px}
        .forge-toolbox .forge-palette-block,.forge-toolbox .event-block,.forge-toolbox .action-block{border-radius:2px;background:#303236}
        .forge-toolbox .forge-palette-block:hover{background:#3c4147}
        .forge-toolbox .forge-workspace section{border-radius:2px;background:#26282b}
        .forge-toolbox .forge-apply{background:#42556b;color:#f1f2f4}
    `;
    dialog.append(style);
    const body = node('div');
    body.className = 'forge-block-body';
    const sidebar = node('aside');
    sidebar.className = 'forge-block-sidebar';
    const search = node('input');
    search.type = 'search';
    search.placeholder = 'Search blocks...';
    search.setAttribute('aria-label', 'Search blocks');
    const tabs = node('nav');
    tabs.className = 'forge-categories';
    tabs.setAttribute('aria-label', 'Block categories');
    const count = node('div');
    count.setAttribute('role', 'status');
    const palette = node('div');
    palette.className = 'forge-palette';
    sidebar.append(search, tabs, count, palette);

    const workspace = node('div');
    workspace.className = 'forge-workspace';
    const list = node('div');
    list.className = 'block-list';
    workspace.append(node('h3', 'Workspace'), list);
    body.append(sidebar, workspace);
    const message = node('footer');
    message.className = 'forge-block-message';
    message.setAttribute('role', 'status');
    dialog.append(header, body, message);

    let category = 'All blocks';
    let activeRule = rules[0];
    let activeBranch = null;
    let dragging = null;
    function decorate(element, entry) {
        element.dataset.color = String(entry.index);
    }
    function dragSource(element, data, label) {
        element.draggable = true;
        element.ondragstart = event => {
            event.stopPropagation();
            dragging = data;
            event.dataTransfer.setData('application/x-forge-block', label);
            event.dataTransfer.effectAllowed = data.rule ? 'move' : 'copy';
        };
        element.ondragend = () => { dragging = null; };
    }
    function dropTarget(element, accepts, receive) {
        element.ondragover = event => {
            if (!dragging || !accepts(dragging)) return;
            event.preventDefault();
            event.stopPropagation();
            event.dataTransfer.dropEffect = dragging.rule ? 'move' : 'copy';
        };
        element.ondrop = event => {
            if (!dragging || !accepts(dragging)) return;
            event.preventDefault();
            event.stopPropagation();
            const block = dragging;
            dragging = null;
            receive(block);
        };
    }
    function addEvent(entry) {
        if (rules.length >= 12) {
            message.textContent = 'A script can have up to 12 events.';
            return;
        }
        activeBranch = null;
        activeRule = {type:entry.type, values:defaults(entry.definition), steps:[]};
        rules.push(activeRule);
        renderWorkspace();
        list.lastChild.scrollIntoView({block:'nearest'});
    }
    function insertAction(block, rule, before) {
        if (!rule) {
            message.textContent = 'Add an event before adding an action.';
            return;
        }
        if (block.step === before && block.step) return;
        if (rule.steps !== block.rule?.steps && rule.steps.length >= 24) {
            message.textContent = 'An event can have up to 24 actions.';
            return;
        }
        const step = block.step || {type:block.entry.type, values:defaults(block.entry.definition)};
        if (!block.step && isControl(step.type)) {
            step.then = [];
            if (step.type === 'ifElse') step.otherwise = [];
        }
        function contains(branch, target) {
            return branch === target || branch.some(item => isControl(item.type) &&
                (contains(item.then,target) || (item.otherwise && contains(item.otherwise,target))));
        }
        if (isControl(step.type) && (contains(step.then,rule.steps) ||
            (step.otherwise && contains(step.otherwise,rule.steps)))) return;
        if (block.rule) block.rule.steps.splice(block.rule.steps.indexOf(step), 1);
        const index = before ? rule.steps.indexOf(before) : rule.steps.length;
        rule.steps.splice(index, 0, step);
        if (rule.owner) {
            activeRule = rule.owner;
            activeBranch = rule;
        } else {
            activeRule = rule;
            activeBranch = null;
        }
        renderWorkspace();
    }
    for (const label of ['All blocks', ...Object.keys(sections)]) {
        const tab = button(label, () => {
            category = label;
            search.value = '';
            renderPalette();
        });
        tabs.append(tab);
    }
    function renderPalette() {
        for (const tab of tabs.children) tab.setAttribute('aria-pressed', String(!search.value.trim() && tab.textContent === category));
        const matching = searchBlocks(search.value, category);
        count.textContent = matching.length + (matching.length === 1 ? ' block' : ' blocks');
        palette.replaceChildren();
        if (!matching.length) palette.append(node('p', 'No matching blocks.'));
        for (const entry of matching) {
            const add = button(entry.definition[0], () => {
                if (entry.category === 'Events') addEvent(entry);
                else insertAction({entry}, activeBranch || activeRule);
            });
            add.className = 'forge-palette-block';
            add.title = blockHelp[entry.type] || (entry.category + ' | Click to add or drag to the workspace');
            add.addEventListener('focus', () => { if (blockHelp[entry.type]) message.textContent = blockHelp[entry.type]; });
            decorate(add, entry);
            dragSource(add, {entry}, entry.definition[0]);
            palette.append(add);
        }
    }
    const isEvent = block => block.entry?.category === 'Events';
    dropTarget(workspace, isEvent, block => addEvent(block.entry));
    function renderWorkspace() {
        list.replaceChildren();
        message.textContent = 'Drag an event into the workspace. Drop actions under an event, or select it and click a block.';
        if (!rules.length) list.append(node('p', 'Start with an event from the block library.'));
        for (const rule of rules) {
            const entry = entryByType[rule.type];
            const section = node('section');
            section.classList.toggle('selected-event', rule === activeRule);
            const heading = node('div');
            heading.className = 'block-row event-block';
            decorate(heading, entry);
            const selectEvent = button(entry.definition[0], () => {
                activeRule = rule;
                activeBranch = null;
                for (const card of list.children) card.classList.toggle('selected-event', card === section);
                for (const selector of list.querySelectorAll('.forge-event-select')) selector.setAttribute('aria-pressed', String(selector === selectEvent));
                message.textContent = 'Click an action to add it to ' + entry.definition[0] + '.';
            });
            selectEvent.className = 'forge-event-select';
            selectEvent.setAttribute('aria-pressed', String(rule === activeRule));
            heading.append(selectEvent, ...fields(entry.definition, rule.values), button('Remove event', () => {
                const index = rules.indexOf(rule);
                rules.splice(index, 1);
                if (activeBranch?.owner === rule) activeBranch = null;
                if (activeRule === rule) activeRule = rules[Math.min(index, rules.length - 1)];
                renderWorkspace();
            }));
            section.append(heading);
            if (blockHelp[rule.type]) section.append(node('p', blockHelp[rule.type]));
            renderBranch(section,rule,rule);
            list.append(section);
        }
    }
    function renderBranch(parent,container,owner) {
        const steps = container.steps;
        steps.forEach((step,index) => {
            const entry = entryByType[step.type];
            const card = node('div');
            const row = node('div');
            row.className = 'block-row action-block';
            decorate(row,entry);
            const handle = node('strong',entry.definition[0]);
            dragSource(handle,{rule:container,step},entry.definition[0]);
            const up = button('Up',() => insertAction({rule:container,step},container,steps[index-1]));
            up.disabled = index === 0;
            const down = button('Down',() => insertAction({rule:container,step},container,steps[index+2]));
            down.disabled = index === steps.length-1;
            row.append(handle,...fields(entry.definition,step.values),up,down,button('Remove',() => {
                steps.splice(index,1);
                activeBranch = null;
                renderWorkspace();
            }));
            dropTarget(row,block => !isEvent(block),block => insertAction(block,container,step));
            card.append(row);
            if (isControl(step.type)) {
                addBranch(step.type === 'repeat' ? 'Do' : 'Then',step.then);
                if (step.type === 'ifElse') addBranch('Else',step.otherwise);
            }
            parent.append(card);

            function addBranch(label,children) {
                const branch = {steps:children,owner};
                const box = node('div');
                box.style.cssText = 'margin:6px 0 6px 22px;padding:5px;border-left:2px solid #95b4d0';
                const selectBranch = button(label,() => {
                    activeRule = owner;
                    activeBranch = branch;
                    renderWorkspace();
                    message.textContent = 'Click a block to add it to ' + label + '.';
                });
                selectBranch.setAttribute('aria-pressed',String(activeBranch?.steps === children));
                if (activeBranch?.steps === children) selectBranch.style.background = '#4e5f6e';
                box.append(selectBranch);
                renderBranch(box,branch,owner);
                card.append(box);
            }
        });
        const dropArea = node('div','Drop block here');
        dropArea.className = 'forge-action-drop';
        parent.append(dropArea);
        dropTarget(parent,block => !isEvent(block),block => insertAction(block,container));
    }
    search.addEventListener('input', renderPalette);
    dialog.addEventListener('close', () => dialog.remove(), {once:true});
    renderPalette();
    renderWorkspace();
    document.body.append(dialog);
    dialog.showModal();
    search.focus();
}