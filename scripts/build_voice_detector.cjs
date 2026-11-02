const fs=require('node:fs'),path=require('node:path'),ts=require('../frontend/node_modules/typescript')
const root=path.resolve(__dirname,'..')
const source=ts.transpileModule(fs.readFileSync(path.join(root,'frontend/src/voiceActivity.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
fs.writeFileSync(path.join(root,'desktop/voice-turn.js'),'// Generated from frontend/src/voiceActivity.ts; run scripts/build_voice_detector.cjs.\n;(function(scope){const exports={};\n'+source+'\nif(typeof module!=="undefined")module.exports={VoiceTurnDetector:exports.VoiceActivity};else scope.VoiceTurnDetector=exports.VoiceActivity;\n})(globalThis)\n')
