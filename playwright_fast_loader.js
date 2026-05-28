'use strict';

const path = require('node:path');

function loadPlaywright() {
  const factoryPath = path.join(__dirname, 'node_modules', 'playwright-core', 'lib', 'inProcessFactory');
  const { createInProcessPlaywright } = require(factoryPath);
  return createInProcessPlaywright();
}

module.exports = { loadPlaywright };
