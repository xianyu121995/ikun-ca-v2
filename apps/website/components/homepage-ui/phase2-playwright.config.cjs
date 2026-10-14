const {defineConfig}=require('./.tools/node_modules/@playwright/test');
const path=require('node:path');
module.exports=defineConfig({
  testDir:path.join(__dirname,'tests'),testMatch:'phase2.spec.cjs',timeout:30000,workers:1,fullyParallel:false,
  use:{baseURL:'http://127.0.0.1:3700',viewport:{width:1920,height:1080},headless:true,
    launchOptions:process.env.PROTOTYPE_CHROMIUM?{executablePath:process.env.PROTOTYPE_CHROMIUM}:{},screenshot:'only-on-failure'},
  reporter:[['list'],['json',{outputFile:path.join(__dirname,'evidence/phase2/test-results.json')}]],
});
