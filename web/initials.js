export function nameInitial(name) {
 return (Array.from(String(name??'').trim())[0] || '?').toLocaleUpperCase('en-US');
}
