// ---------- particle field ----------
const canvas = document.getElementById('fx');
const ctx = canvas.getContext('2d');
let W, H, particles;

function resize(){
  W = canvas.width = window.innerWidth;
  H = canvas.height = window.innerHeight;
}
function makeParticles(){
  const count = Math.floor((W * H) / 32000);
  particles = Array.from({length: count}, () => ({
    x: Math.random() * W,
    y: Math.random() * H,
    r: Math.random() * 1.6 + 0.4,
    vx: (Math.random() - 0.5) * 0.15,
    vy: (Math.random() - 0.5) * 0.15,
    a: Math.random() * 0.5 + 0.15
  }));
}
resize(); makeParticles();
window.addEventListener('resize', () => { resize(); makeParticles(); });

let particleColor = { r: 79, g: 70, b: 229 };
function hexToRgb(hex){
  const m = hex.trim().match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i);
  return m ? { r: parseInt(m[1],16), g: parseInt(m[2],16), b: parseInt(m[3],16) } : particleColor;
}
function refreshParticleColor(){
  const t1 = getComputedStyle(document.body).getPropertyValue('--t1');
  if (t1) particleColor = hexToRgb(t1);
}
refreshParticleColor();

function tick(){
  ctx.clearRect(0, 0, W, H);
  // constellation links between nearby particles
  for (let i = 0; i < particles.length; i++){
    for (let j = i + 1; j < particles.length; j++){
      const a = particles[i], b = particles[j];
      const dx = a.x - b.x, dy = a.y - b.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 130) {
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = `rgba(${particleColor.r},${particleColor.g},${particleColor.b},${0.12 * (1 - dist / 130)})`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }
  }
  particles.forEach(p => {
    p.x += p.vx; p.y += p.vy;
    if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
    if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${particleColor.r},${particleColor.g},${particleColor.b},${p.a * 0.35})`;
    ctx.fill();
  });
  requestAnimationFrame(tick);
}
tick();

// ---------- topbar + progress ----------
const topbar = document.getElementById('topbar');
const progressbar = document.getElementById('progressbar');
const scroller = document.body;

scroller.addEventListener('scroll', () => {
  topbar.classList.toggle('scrolled', scroller.scrollTop > 20);
  const pct = scroller.scrollTop / (scroller.scrollHeight - window.innerHeight) * 100;
  progressbar.style.width = pct + '%';
});

// ---------- rail ----------
const slides = document.querySelectorAll('.slide');
const rail = document.getElementById('rail');

slides.forEach((sec) => {
  const dot = document.createElement('div');
  dot.className = 'dot';
  const label = sec.dataset.rail || '';
  dot.innerHTML = `<span class="lbl">${label}</span>`;
  dot.addEventListener('click', () => sec.scrollIntoView({behavior:'smooth'}));
  rail.appendChild(dot);
});
const dots = rail.querySelectorAll('.dot');

const railObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const idx = Array.from(slides).indexOf(entry.target);
      dots.forEach(d => d.classList.remove('active'));
      dots[idx].classList.add('active');
    }
  });
}, { threshold: 0.6 });
slides.forEach(sec => railObserver.observe(sec));

// ---------- reveal on view (each slide, including each lone sub-step) ----------
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('in-view');
      // switch the whole page's theme palette to match this step's animation family
      const theme = entry.target.dataset.step || entry.target.dataset.parent;
      if (theme) { document.body.setAttribute('data-theme', theme); refreshParticleColor(); }
    } else {
      // allow re-triggering the "light" animation each time a sub-step re-enters
      if (entry.target.classList.contains('sub-slide')) {
        entry.target.classList.remove('in-view');
      }
    }
  });
}, { threshold: 0.45 });
slides.forEach(sec => revealObserver.observe(sec));

// ---------- CTA ----------
const cta = document.querySelector('.cta-btn');
if (cta) {
  cta.addEventListener('click', () => {
    window.open('https://ahmedmmohamed052-stack.github.io/IntelligentEra/#contact', '_blank');
  });
}
