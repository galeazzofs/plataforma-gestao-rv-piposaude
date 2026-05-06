// Karma config for the shadow-cljs `:karma` test build.
// shadow-cljs compiles `frontend/test/**` into `target/test/test.js`; this
// config tells Karma to load that bundle, run it under headless Chrome, and
// kick off the cljs.test runner via the karma-cljs-test adapter.
module.exports = function (config) {
  config.set({
    browsers: ['ChromeHeadless'],
    basePath: 'target/test',
    files: ['test.js'],
    frameworks: ['cljs-test'],
    plugins: ['karma-cljs-test', 'karma-chrome-launcher'],
    client: {
      // Tells karma-cljs-test which entry point to call. Matches the symbol
      // shadow-cljs emits for `:target :karma`.
      args: ['shadow.test.karma.init']
    },
    colors: true,
    logLevel: config.LOG_INFO,
    singleRun: true,
    autoWatch: false
  });
};
