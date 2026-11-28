import { readFileSync } from "node:fs";

const mode = process.argv[2];
const raw = readFileSync(0);
if (raw.length > 256 * 1024 || !raw.length || !["mathml", "svg"].includes(mode)) process.exit(2);
const value = raw.toString("utf8");

if (mode === "mathml") {
  globalThis.MathJax = {
    loader: {
      paths: {mathjax: "@mathjax/src/bundle"},
      load: ["input/mml", "output/svg", "adaptors/liteDOM"],
      require: file => import(file)
    },
    startup: {typeset: false},
    output: {font: "mathjax-newcm"},
    svg: {fontCache: "none"}
  };
  await import("@mathjax/src/bundle/startup.js");
  const mj = globalThis.MathJax;
  await mj.startup.promise;
  try {
    const node = await mj.mathml2svgPromise(value, {display: true, em: 16, ex: 8, containerWidth: 1024});
    const adaptor = mj.startup.adaptor;
    const svg = adaptor.tags(node, "svg")[0];
    if (!svg || adaptor.tags(svg, "g").some(g => adaptor.getAttribute(g, "data-mml-node") === "merror")) {
      process.exitCode = 2;
    } else {
      const result = adaptor.serializeXML(svg);
      if (Buffer.byteLength(result) > 256 * 1024) process.exitCode = 2;
      else process.stdout.write(result);
    }
  } catch {
    process.exitCode = 2;
  } finally {
    mj.done();
  }
} else {
  const {Resvg} = await import("@resvg/resvg-js");
  try {
    const result = new Resvg(value, {background: "#ffffff", font: {loadSystemFonts: false}}).render();
    if (result.width > 1024 || result.height > 600 || !result.width || !result.height) {
      process.exitCode = 2;
    } else {
      const png = result.asPng();
      if (png.length > 1024 * 1024) process.exitCode = 2;
      else process.stdout.write(png);
    }
  } catch {
    process.exitCode = 2;
  }
}
