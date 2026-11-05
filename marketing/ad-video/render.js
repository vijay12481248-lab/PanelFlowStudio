// Usage: node render.js <playwright-core dir> <out.mp4> [audio.wav] [fps] [onlyTimes,comma]
const path=require('path'),{spawn}=require('child_process');
const {chromium}=require(path.join(process.argv[2],'node_modules','playwright-core'));
const [,, , out, audio, fpsA, only]=process.argv;
const FPS=+(fpsA||30);
(async()=>{
  const b=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const p=await b.newPage({viewport:{width:1920,height:1080}});
  p.on('pageerror',e=>console.error('PAGEERR',e.message));
  await p.goto(require('url').pathToFileURL(path.join(__dirname,'ad.html')).href);
  await p.waitForFunction(()=>window.seek);
  if(only){ // still frames for review
    for(const t of only.split(',')){await p.evaluate(t=>seek(t),+t);await p.screenshot({path:path.join(path.dirname(out),`f_${t}.png`)});}
    return b.close();
  }
  const dur=await p.evaluate(()=>DUR),n=Math.round(dur*FPS);
  const args=['-y','-f','image2pipe','-framerate',String(FPS),'-i','-',...(audio?['-i',audio]:[]),'-c:v','libx264','-preset','slow','-crf','16','-pix_fmt','yuv420p',...(audio?['-c:a','aac','-b:a','256k','-shortest']:[]),'-movflags','+faststart',out];
  const ff=spawn('ffmpeg',args,{stdio:['pipe','inherit','inherit']});
  for(let i=0;i<n;i++){
    await p.evaluate(t=>seek(t),i/FPS);
    const buf=await p.screenshot({type:'png'});
    if(!ff.stdin.write(buf))await new Promise(r=>ff.stdin.once('drain',r));
  }
  ff.stdin.end();await new Promise(r=>ff.on('close',r));await b.close();
})();
