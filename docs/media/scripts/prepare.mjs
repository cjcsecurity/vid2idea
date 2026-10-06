import { mkdir, copyFile, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Build two fully local projects. The optional dependency root reuses a
// verified installation; it never changes the HTML or fetches render assets.
const mediaRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dependencyRoot = process.env.MEDIA_NODE_MODULES || join(mediaRoot, 'node_modules');
const outputRoot = resolve(process.argv[2] || join(mediaRoot, '.build'));
const assets = {
  'gsap.min.js': 'gsap/dist/gsap.min.js',
  'manrope.woff2': '@fontsource-variable/manrope/files/manrope-latin-wght-normal.woff2',
  'jetbrains-mono.woff2': '@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2',
};
const template = await readFile(join(mediaRoot, 'src', 'story.html'), 'utf8');
for (const project of ['demo', 'loop']) {
  const root = join(outputRoot, project);
  await mkdir(join(root, 'assets'), { recursive: true });
  const demo = project === 'demo';
  const values = { ID: `vid2idea-${project}`, VARIANT: project, WIDTH: demo ? 1600 : 960,
    HEIGHT: demo ? 900 : 540, SCALE: demo ? 1600 / 960 : 1,
    DURATION: demo ? 22 : 12, FPS: demo ? 30 : 25 };
  const html = template.replace(/__([A-Z]+)__/g, (_, key) => {
    if (!(key in values)) throw new Error(`Unknown composition variable: ${key}`);
    return String(values[key]);
  });
  await writeFile(join(root, 'index.html'), html);
  await copyFile(join(mediaRoot, 'src', `${project}.motion.json`), join(root, 'index.motion.json'));
  await copyFile(join(mediaRoot, 'src', 'frameforge.svg'), join(root, 'assets', 'frameforge.svg'));
  for (const [target, source] of Object.entries(assets)) {
    await copyFile(join(dependencyRoot, source), join(root, 'assets', target));
  }
  await writeFile(join(root, 'hyperframes.json'), JSON.stringify({ name: `vid2idea-${project}`, skill: project === 'demo' ? 'brag' : 'motion-graphics' }, null, 2));
}
console.log(outputRoot);
