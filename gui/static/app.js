'use strict';

/* Novellstudion — klient. Ingen ram, inga beroenden. */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const S = {
  boot: null,
  brief: {},
  llm: {},
  save: {},
  styleCard: '',
  draft: '',
  hits: [],
  hitsStale: true,
  hitsCount: 0,
  prompt: '',
  promptStats: null,
  lastGenerated: null,
  streaming: false,
  editing: false,
  abort: null,
  conn: null,
  savedPath: '',
  history: [],
  folderDir: '',
  folderPath: '',
  renderQueued: false,
  autoScroll: true,
  promptDirty: true,
  promptSeq: 0,
  previewTimer: null,
  stateTimer: null,
};

const KIND_LABEL = { openai: 'OpenAI-format', ollama: 'Ollama', 'llama.cpp': 'llama.cpp' };

const EXAMPLES = {
  koket: {
    scene: 'Ett kök sent på kvällen. Två grannar som känt varandra i tio år. Hon har bestämt sig för att säga något. Han vet det inte. Scenen slutar utan att det blir sagt.',
    place: 'ett kök, sent på kvällen',
    characters: 'två grannar i fyrtioårsåldern',
    stakes: 'hon har bestämt sig för att säga något, han vet det inte',
    tone: 'lågmäld',
    ending: 'öppet',
  },
  taget: {
    scene: 'En sovvagn på nattåget mot norr. Två främlingar delar kupé. Lampan är släckt, men ingen sover. Samtalet börjar om något oviktigt och slutar någon annanstans.',
    place: 'en sovvagn på nattåget mot norr',
    characters: 'två främlingar, en kvinna och en man, båda vuxna',
    stakes: 'morgonen kommer och de ska aldrig ses igen',
    tone: 'spänd',
    ending: 'eftertänksamt',
  },
  stugan: {
    scene: 'En stuga vid en sjö i november. Regnet mot fönstret. Hon är där för att vara ensam, men någon står redan på trappan. Ingen av dem säger varför.',
    place: 'en stuga vid en sjö i november',
    characters: 'en kvinna och en man som inte setts på år',
    stakes: 'de har en natt på sig att säga sanningen',
    tone: 'melankolisk',
    ending: 'öppet',
  },
};

/* ------------------------------------------------------------------ nytta */

function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function countWords(text) {
  const matches = String(text || '').match(/[A-Za-zÅÄÖåäöÉéÜü]+/g);
  return matches ? matches.length : 0;
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString('sv-SE');
}

function basename(path) {
  if (!path) return '';
  const parts = String(path).split(/[\\/]/);
  return parts[parts.length - 1];
}

function svTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString('sv-SE', {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function toast(message, kind = 'info', detail = '') {
  const wrap = $('#toasts');
  if (!wrap) return;
  const node = document.createElement('div');
  node.className = `toast ${kind}`;
  node.appendChild(document.createTextNode(message));
  if (detail) {
    const small = document.createElement('small');
    small.textContent = detail;
    node.appendChild(small);
  }
  wrap.appendChild(node);
  setTimeout(() => {
    node.style.transition = 'opacity .25s, transform .25s';
    node.style.opacity = '0';
    node.style.transform = 'translateY(6px)';
    setTimeout(() => node.remove(), 260);
  }, kind === 'error' ? 8000 : 4200);
}

async function apiGet(url) {
  const response = await fetch(url, { headers: { Accept: 'application/json' } });
  let data = {};
  try { data = await response.json(); } catch (error) { /* tomt svar */ }
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

async function apiPost(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  let data = {};
  try { data = await response.json(); } catch (error) { /* tomt svar */ }
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

/* ------------------------------------------------------------------ start */

document.addEventListener('DOMContentLoaded', init);

async function init() {
  try {
    const data = await apiGet('/api/bootstrap');
    S.boot = data;

    S.brief = { ...data.defaults.brief, ...(data.state.brief || {}) };
    S.llm = { ...data.defaults.llm, ...(data.state.llm || {}) };
    S.save = { ...data.defaults.save, ...(data.state.save || {}) };
    S.styleCard = data.style_card || '';
    S.history = data.history || [];

    normalizeState();
    buildStaticUI(data);
    syncUI();
    wire();
    renderWordChips();
    updateLabels();
    updatePathPreview();
    updateDocumentTitle();
    renderPaper();
    checkGate();

    if (S.llm.base_url) {
      connect(true);
    } else {
      setConnection('idle', 'Inte ansluten');
    }
    updatePromptPlaceholder();
  } catch (error) {
    toast(`Kunde inte starta gränssnittet: ${error.message}`, 'error');
  }
}

async function resetApp() {
  const question = [
    'Nollställa allt?',
    '',
    'Inställningar, historik och 18+-spärren nollställs.',
    'Sparade noveller flyttas till en backup-mapp i stället för att raderas.',
  ].join('\n');
  if (!window.confirm(question)) return;

  const button = $('#resetBtn');
  if (button) button.disabled = true;
  try {
    const data = await apiPost('/api/reset');
    try {
      localStorage.removeItem('novellstudion-adult');
    } catch (error) {
      /* localStorage kan vara avstängt */
    }
    toast('Nollställning klar. Sidan laddas om…', 'success', data.backup || '');
    setTimeout(() => location.reload(), 2600);
  } catch (error) {
    if (button) button.disabled = false;
    toast(`Nollställning misslyckades: ${error.message}`, 'error');
  }
}

function normalizeState() {
  const brief = S.brief;
  brief.length = Math.min(5000, Math.max(300, Number(brief.length) || 1200));
  brief.sex_level = Math.min(5, Math.max(1, Number(brief.sex_level) || 3));
  brief.k = Math.min(6, Math.max(0, Number(brief.k) || 0));
  brief.per_story = Math.min(3, Math.max(1, Number(brief.per_story) || 1));
  brief.words_include = Array.isArray(brief.words_include)
    ? brief.words_include.map(String).filter(Boolean).slice(0, 60)
    : [];
  brief.words_avoid = Array.isArray(brief.words_avoid)
    ? brief.words_avoid.map(String).filter(Boolean)
    : [];
  brief.exclude_ids = Array.isArray(brief.exclude_ids)
    ? brief.exclude_ids.map(Number).filter(Number.isFinite)
    : [];
  brief.use_style_card = brief.use_style_card !== false;
  brief.category_filter = brief.category_filter !== false;
  brief.search_query = brief.search_query || '';

  S.llm.temperature = Number(S.llm.temperature) || 0.85;
  S.llm.top_p = Number(S.llm.top_p) || 0.9;
  S.llm.max_tokens = Number(S.llm.max_tokens) || 0;
  const rawPenalty = Number(S.llm.repeat_penalty) || 1.2;
  S.llm.repeat_penalty = Math.min(1.5, rawPenalty < 1.1 ? 1.2 : rawPenalty);
  S.llm.model = S.llm.model || '';
  S.llm.base_url = S.llm.base_url || '';
  S.llm.kind = S.llm.kind || 'openai';
  S.llm.remember_key = S.llm.remember_key === true;
  S.llm.api_key = S.llm.api_key || '';
  S.llm.disable_thinking = S.llm.disable_thinking !== false;
  S.llm.context = Number(S.llm.context) || 0;

  S.save.folder = S.save.folder || 'out/noveller';
  S.save.filename = S.save.filename || '';
  S.save.autosave = S.save.autosave !== false;
}

/* -------------------------------------------------------------- statiska UI */

function buildStaticUI(data) {
  const stats = data.db || {};
  if (stats.ok) {
    $('#brandSub').textContent =
      `${formatNumber(stats.stories)} noveller · ${(stats.words / 1e6).toFixed(1).replace('.', ',')} M ord`;
  } else {
    $('#brandSub').textContent = 'index saknas — kör build';
  }

  const category = $('#category');
  category.innerHTML = '<option value="">Alla kategorier</option>';
  for (const item of data.categories || []) {
    const option = document.createElement('option');
    option.value = item.key;
    option.textContent = `${item.label} (${item.count})`;
    category.appendChild(option);
  }

  fillSelect('#tone', (data.tones || []).map((tone) => ({ value: tone, label: tone })));
  fillSelect('#ending', (data.endings || []).map((ending) => ({ value: ending, label: ending })));
  fillSelect('#pov', data.pov || []);
  fillSelect('#tense', data.tense || []);
  fillSelect('#dialogue', data.dialogue || []);

  const presets = $('#lengthPresets');
  presets.innerHTML = '';
  for (const preset of data.length_presets || []) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'chip';
    button.dataset.words = String(preset.words);
    button.textContent = String(preset.words);
    button.title = `${preset.label} — ${preset.words} ord`;
    presets.appendChild(button);
  }

  const seg = $('#sexSeg');
  seg.innerHTML = '';
  for (const level of data.sex_levels || []) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.level = String(level.level);
    button.title = level.description;
    button.innerHTML = `<b>${level.level}</b><small>${escapeHtml(level.short)}</small>`;
    seg.appendChild(button);
  }

  $('#styleCardPreview').textContent = S.styleCard || 'Stilkortet kunde inte läsas.';
  $('#searchQuery').value = S.brief.search_query || '';

  const list = document.createElement('datalist');
  list.id = 'addrHints';
  for (const address of ['127.0.0.1:8088', '192.168.1.139:8089', '127.0.0.1:11434', '127.0.0.1:1234']) {
    const option = document.createElement('option');
    option.value = address;
    list.appendChild(option);
  }
  document.body.appendChild(list);
  $('#baseUrl').setAttribute('list', 'addrHints');
}

function fillSelect(selector, options) {
  const select = $(selector);
  if (!select) return;
  select.innerHTML = '';
  for (const item of options) {
    const option = document.createElement('option');
    option.value = item.value;
    option.textContent = item.label;
    select.appendChild(option);
  }
}

/* ---------------------------------------------------------------- synka UI */

function syncUI() {
  const brief = S.brief;
  const llm = S.llm;
  const save = S.save;

  setValue('#title', brief.title);
  setValue('#scene', brief.scene);
  setValue('#place', brief.place);
  setValue('#characters', brief.characters);
  setValue('#stakes', brief.stakes);
  setValue('#extra', brief.extra);
  setValue('#wordsAvoid', (brief.words_avoid || []).join(', '));
  setValue('#length', brief.length);
  setValue('#k', brief.k);
  setValue('#perStory', brief.per_story);
  setCheck('#categoryFilter', brief.category_filter);
  setCheck('#useStyleCard', brief.use_style_card);
  setSelectValue('#category', brief.category || '');
  setSelectValue('#tone', brief.tone || 'lågmäld');
  setSelectValue('#ending', brief.ending || 'öppet');
  setSelectValue('#pov', brief.pov || 'auto');
  setSelectValue('#tense', brief.tense || 'auto');
  setSelectValue('#dialogue', brief.dialogue || 'auto');

  setValue('#folder', save.folder);
  setValue('#filename', save.filename);
  setCheck('#autosave', save.autosave);

  setValue('#baseUrl', llm.base_url);
  setValue('#temperature', llm.temperature);
  setValue('#topP', llm.top_p);
  setValue('#maxTokens', llm.max_tokens);
  setValue('#seed', llm.seed == null ? '' : llm.seed);
  setValue('#repeatPenalty', llm.repeat_penalty);
  setValue('#apiKey', llm.api_key || '');
  setCheck('#rememberKey', llm.remember_key);
  setCheck('#disableThinking', llm.disable_thinking);

  if (llm.model) {
    $('#modelManual').value = llm.model;
  }

  $$('#sexSeg button').forEach((button) => {
    button.classList.toggle('on', Number(button.dataset.level) === brief.sex_level);
  });
  const sceneMore = $('#sceneMore');
  if (sceneMore) {
    sceneMore.open = Boolean(
      (brief.place || '').trim() || (brief.characters || '').trim() || (brief.stakes || '').trim(),
    );
  }
  $('#searchQuery').value = brief.search_query || '';
  renderChosenWords();
  updateContextWarning();
}

function setValue(selector, value) {
  const el = $(selector);
  if (el) el.value = value == null ? '' : value;
}

function setCheck(selector, value) {
  const el = $(selector);
  if (el) el.checked = Boolean(value);
}

function setSelectValue(selector, value) {
  const select = $(selector);
  if (!select) return;
  let found = Array.from(select.options).some((option) => option.value === value);
  if (!found && value) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
    found = true;
  }
  select.value = found ? value : (select.options[0] ? select.options[0].value : '');
}

/* ---------------------------------------------------------------- händelser */

function wire() {
  bindText('#title', 'title');
  bindText('#scene', 'scene');
  bindText('#place', 'place');
  bindText('#characters', 'characters');
  bindText('#stakes', 'stakes');
  bindText('#extra', 'extra');
  bindText('#searchQuery', 'search_query', { preview: false });

  bindSelect('#category', 'category');
  bindSelect('#tone', 'tone');
  bindSelect('#ending', 'ending');
  bindSelect('#pov', 'pov');
  bindSelect('#tense', 'tense');
  bindSelect('#dialogue', 'dialogue');
  $('#resetBtn').addEventListener('click', resetApp);

  $('#length').addEventListener('input', (event) => {
    S.brief.length = Number(event.target.value);
    updateLabels();
    changed();
  });

  $('#lengthPresets').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-words]');
    if (!chip) return;
    S.brief.length = Number(chip.dataset.words);
    $('#length').value = S.brief.length;
    updateLabels();
    changed();
  });

  $('#sexSeg').addEventListener('click', (event) => {
    const button = event.target.closest('[data-level]');
    if (!button) return;
    S.brief.sex_level = Number(button.dataset.level);
    $$('#sexSeg button').forEach((node) => {
      node.classList.toggle('on', Number(node.dataset.level) === S.brief.sex_level);
    });
    renderWordChips();
    updateLabels();
    changed();
  });

  $('#wordChips').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-word]');
    if (!chip) return;
    toggleWord(chip.dataset.word);
  });

  $('#chosenWords').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-word]');
    if (!chip) return;
    removeWord(chip.dataset.word);
  });

  $('#wordAdd').addEventListener('click', addWordFromInput);
  $('#wordInput').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      addWordFromInput();
    }
  });

  $('#wordsAvoid').addEventListener('input', (event) => {
    S.brief.words_avoid = event.target.value
      .split(/[,;]/)
      .map((word) => word.trim())
      .filter(Boolean);
    changed();
  });

  $('#k').addEventListener('input', (event) => {
    S.brief.k = Number(event.target.value);
    updateLabels();
    changed();
  });
  $('#perStory').addEventListener('input', (event) => {
    S.brief.per_story = Number(event.target.value);
    updateLabels();
    changed();
  });
  $('#categoryFilter').addEventListener('change', (event) => {
    S.brief.category_filter = event.target.checked;
    changed();
  });
  $('#useStyleCard').addEventListener('change', (event) => {
    S.brief.use_style_card = event.target.checked;
    changed();
  });

  $('#folder').addEventListener('input', (event) => {
    S.save.folder = event.target.value;
    updatePathPreview();
    persistSoon();
  });
  $('#filename').addEventListener('input', (event) => {
    S.save.filename = event.target.value;
    updatePathPreview();
    persistSoon();
  });
  $('#autosave').addEventListener('change', (event) => {
    S.save.autosave = event.target.checked;
    persistSoon();
  });

  $('#baseUrl').addEventListener('change', (event) => {
    S.llm.base_url = event.target.value.trim();
    persistSoon();
  });
  $('#baseUrl').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      connect(false);
    }
  });
  $('#connectBtn').addEventListener('click', () => connect(false));

  $('#modelSelect').addEventListener('change', (event) => {
    if (!event.target.value) return;
    S.llm.model = event.target.value;
    persistSoon();
  });
  $('#modelManual').addEventListener('input', (event) => {
    S.llm.model = event.target.value.trim();
    persistSoon();
  });

  bindRange('#temperature', '#tempOut', 'temperature', 2);
  bindRange('#topP', '#topPOut', 'top_p', 2);
  bindRange('#repeatPenalty', '#repeatOut', 'repeat_penalty', 2);
  $('#temperature').addEventListener('input', (event) => {
    S.llm.temperature = Number(event.target.value);
    persistSoon();
  });
  $('#topP').addEventListener('input', (event) => {
    S.llm.top_p = Number(event.target.value);
    persistSoon();
  });
  $('#repeatPenalty').addEventListener('input', (event) => {
    S.llm.repeat_penalty = Number(event.target.value);
    persistSoon();
  });
  $('#maxTokens').addEventListener('input', (event) => {
    S.llm.max_tokens = Number(event.target.value) || 0;
    updateLabels();
    persistSoon();
  });
  $('#seed').addEventListener('input', (event) => {
    S.llm.seed = event.target.value === '' ? null : Number(event.target.value);
    persistSoon();
  });
  $('#apiKey').addEventListener('input', (event) => {
    S.llm.api_key = event.target.value;
    persistSoon();
  });
  $('#rememberKey').addEventListener('change', (event) => {
    S.llm.remember_key = event.target.checked;
    persistSoon();
  });
  $('#disableThinking').addEventListener('change', (event) => {
    S.llm.disable_thinking = event.target.checked;
    persistSoon();
  });

  $('#generateBtn').addEventListener('click', () => generate('new'));
  $('#continueBtn').addEventListener('click', () => generate('continue'));
  $('#stopBtn').addEventListener('click', stopGeneration);

  $('#saveBtn').addEventListener('click', saveNow);
  $('#editBtn').addEventListener('click', toggleEditing);
  $('#copyBtn').addEventListener('click', copyDraft);
  $('#downloadBtn').addEventListener('click', downloadDraft);
  $('#clearBtn').addEventListener('click', clearDraft);
  $('#openFolderBtn').addEventListener('click', () => revealPath(S.save.folder));

  $$('.tab').forEach((tab) => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });

  $('#rebuildPromptBtn').addEventListener('click', () => refreshPrompt(true));
  $('#copyPromptBtn').addEventListener('click', () => copyText($('#promptText').value, 'Prompten kopierad.'));
  $('#useEdited').addEventListener('change', () => {
    if ($('#useEdited').checked) {
      toast('Modellen får nu exakt den text som står i rutan.', 'info');
    }
  });
  $('#promptText').addEventListener('input', () => {
    S.promptDirty = true;
  });

  $('#ragSearchBtn').addEventListener('click', doRagSearch);
  $('#searchQuery').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      doRagSearch();
    }
  });

  $('#libraryBtn').addEventListener('click', openLibrary);
  $('#libraryClose').addEventListener('click', () => $('#library').classList.add('hidden'));
  $('#libraryList').addEventListener('click', onLibraryClick);

  $('#browseBtn').addEventListener('click', () => openFolder(S.save.folder));
  $('#destBtn').addEventListener('click', () => openFolder(S.save.folder));
  $('#folderClose').addEventListener('click', closeFolder);
  $('#folderCancel').addEventListener('click', closeFolder);
  $('#folderChoose').addEventListener('click', chooseFolder);
  $('#folderGo').addEventListener('click', () => loadFolder($('#folderPath').value));
  $('#folderPath').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') loadFolder($('#folderPath').value);
  });
  $('#folderList').addEventListener('click', (event) => {
    const row = event.target.closest('[data-path]');
    if (row) loadFolder(row.dataset.path);
  });
  $('#folderPlaces').addEventListener('click', (event) => {
    const place = event.target.closest('[data-path]');
    if (place) loadFolder(place.dataset.path);
  });
  $('#folderNewBtn').addEventListener('click', createFolder);
  $('#folderNewName').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      createFolder();
    }
  });

  $('#helpBtn').addEventListener('click', () => $('#helpModal').classList.remove('hidden'));
  $('#contextHelp').addEventListener('click', () => {
    $('#helpModal').classList.remove('hidden');
    const section = $('#help-context');
    if (section) section.scrollIntoView({ block: 'start' });
  });
  $('#contextFit').addEventListener('click', () => {
    S.brief.k = 1;
    S.brief.length = 600;
    $('#k').value = 1;
    $('#length').value = 600;
    updateLabels();
    changed();
    toast(
      'Justerat till 1 stilprov och 600 ord — det ryms i en liten kontext. Höj -c i llama.cpp för fler prover och längre texter.',
      'info',
    );
  });
  $('#helpClose').addEventListener('click', () => $('#helpModal').classList.add('hidden'));

  $('#gateBtn').addEventListener('click', () => {
    localStorage.setItem('novellstudion-adult', '1');
    $('#gate').classList.add('hidden');
    $('#scene').focus();
  });

  $$('.examples .chip').forEach((chip) => {
    chip.addEventListener('click', () => applyExample(chip.dataset.example));
  });

  const body = $('.work-body');
  body.addEventListener('scroll', () => {
    const distance = body.scrollHeight - body.scrollTop - body.clientHeight;
    S.autoScroll = distance < 140;
  });

  $('#prose').addEventListener('input', () => {
    if (!S.editing) return;
    S.draft = $('#prose').innerText.replace(/\u00a0/g, ' ').trim();
    updateWordBadge();
  });

  document.addEventListener('keydown', onKeydown);
  window.addEventListener('beforeunload', (event) => {
    if (S.streaming) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
}

function bindText(selector, key, options = {}) {
  const el = $(selector);
  if (!el) return;
  el.addEventListener('input', () => {
    S.brief[key] = el.value;
    if (options.preview !== false) changed();
    if (key === 'title') updateDocumentTitle();
  });
}

function bindSelect(selector, key) {
  const el = $(selector);
  if (!el) return;
  el.addEventListener('change', () => {
    S.brief[key] = el.value;
    changed();
  });
}

function bindRange(selector, outputSelector, key, decimals) {
  const el = $(selector);
  const output = $(outputSelector);
  if (!el || !output) return;
  el.addEventListener('input', () => {
    output.textContent = Number(el.value).toFixed(decimals).replace('.', ',');
    S.llm[key] = Number(el.value);
  });
}

function changed() {
  S.promptDirty = true;
  if (!$('#useEdited').checked && isEditingTab()) schedulePreview();
  persistSoon();
}

function isEditingTab() {
  const active = $('.tab.active');
  const name = active ? active.dataset.tab : 'text';
  return name === 'prompt' || name === 'rag';
}

function schedulePreview() {
  clearTimeout(S.previewTimer);
  S.previewTimer = setTimeout(() => {
    if (!S.streaming) refreshPrompt(false);
  }, 700);
}

/* ---------------------------------------------------------------- sexgrad */

function renderWordChips() {
  const wrap = $('#wordChips');
  const level = S.brief.sex_level || 3;
  const included = new Set(S.brief.words_include.map((word) => word.toLowerCase()));
  const seen = new Set();
  wrap.innerHTML = '';

  for (let current = 1; current <= level; current += 1) {
    const words = (S.boot.word_presets && S.boot.word_presets[String(current)]) || [];
    for (const word of words) {
      const key = word.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chip' + (included.has(key) ? ' on' : '');
      chip.dataset.word = word;
      chip.title = `Nivå ${current}`;
      chip.innerHTML = `<span class="lv">${current}</span>${escapeHtml(word)}`;
      wrap.appendChild(chip);
    }
  }
}

function renderChosenWords() {
  const wrap = $('#chosenWords');
  wrap.innerHTML = '';
  const words = S.brief.words_include || [];
  if (!words.length) {
    const hint = document.createElement('span');
    hint.className = 'hint';
    hint.textContent = 'Inga valda ord — modellen får välja själv.';
    wrap.appendChild(hint);
    return;
  }
  for (const word of words) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip chosen';
    chip.dataset.word = word;
    chip.textContent = word;
    chip.title = 'Ta bort';
    wrap.appendChild(chip);
  }
}

function toggleWord(word) {
  const key = word.toLowerCase();
  const current = S.brief.words_include || [];
  const exists = current.some((item) => item.toLowerCase() === key);
  if (exists) {
    S.brief.words_include = current.filter((item) => item.toLowerCase() !== key);
  } else {
    if (current.length >= 60) {
      toast('Max 60 ord. Ta bort något först.', 'warn');
      return;
    }
    S.brief.words_include = [...current, word];
  }
  renderWordChips();
  renderChosenWords();
  changed();
}

function removeWord(word) {
  const key = word.toLowerCase();
  S.brief.words_include = S.brief.words_include.filter((item) => item.toLowerCase() !== key);
  renderWordChips();
  renderChosenWords();
  changed();
}

function addWordFromInput() {
  const input = $('#wordInput');
  const value = input.value.trim();
  if (!value) return;
  const existing = S.brief.words_include.some((word) => word.toLowerCase() === value.toLowerCase());
  if (!existing && S.brief.words_include.length < 60) {
    S.brief.words_include = [...S.brief.words_include, value];
    renderWordChips();
    renderChosenWords();
    changed();
  }
  input.value = '';
  input.focus();
}

/* ---------------------------------------------------------------- etiketter */

function updateLabels() {
  const length = S.brief.length;
  const pages = (length / 300).toFixed(1).replace('.', ',');
  $('#lengthOut').textContent = `${formatNumber(length)} ord · ca ${pages} sidor`;

  const levelInfo = (S.boot.sex_levels || []).find((item) => item.level === S.brief.sex_level);
  $('#sexOut').textContent = levelInfo
    ? `${levelInfo.level} · ${levelInfo.label}`
    : String(S.brief.sex_level);
  $('#sexDesc').textContent = levelInfo ? levelInfo.description : '';

  $('#kOut').textContent = S.brief.k === 0 ? 'av' : String(S.brief.k);
  $('#perStoryOut').textContent = String(S.brief.per_story);
  $('#tempOut').textContent = Number(S.llm.temperature).toFixed(2).replace('.', ',');
  $('#topPOut').textContent = Number(S.llm.top_p).toFixed(2).replace('.', ',');
  $('#repeatOut').textContent = Number(S.llm.repeat_penalty).toFixed(2).replace('.', ',');

  const autoTokens = Math.max(512, Math.min(16384, Math.round(length * 2.3) + 200));
  const ctxNote = S.llm.context
    ? ` Serverns kontext: ${formatNumber(S.llm.context)} tokens.`
    : '';
  const hint = S.llm.max_tokens > 0
    ? `Hård gräns: ${formatNumber(S.llm.max_tokens)} tokens. Prompten tillkommer.${ctxNote}`
    : `Automatiskt: ca ${formatNumber(autoTokens)} tokens för svaret (prompten tillkommer).${ctxNote}`;
  $('#maxTokensHint').textContent = hint;
}

function updatePathPreview() {
  const folder = (S.save.folder || '').trim() || 'out/noveller';
  const auto = S.save.filename ? S.save.filename : 'automatiskt filnamn';
  $('#pathPreview').textContent = `→ ${folder.replace(/[\\/]$/, '')}\\${auto}`;
  const dest = $('#destBtn');
  if (dest) {
    dest.textContent = folder;
    dest.title = `Sparas i ${folder} — klicka för att byta mapp`;
  }
}

function updateContextWarning() {
  const el = $('#contextWarning');
  if (!el) return;
  const context = Number((S.conn && S.conn.context) || S.llm.context || 0);
  if (context > 0 && context < 4096) {
    $('#contextWarningText').textContent =
      `Kontexten är bara ${formatNumber(context)} tokens.`;
    el.classList.remove('hidden');
  } else {
    el.classList.add('hidden');
  }
}

function updateDocumentTitle() {
  const title = (S.brief.title || '').trim();
  document.title = title ? `${title} · Novellstudion` : 'Novellstudion · stil-lab';
}

function updatePromptPlaceholder() {
  if (!S.prompt) {
    $('#promptText').placeholder =
      'Prompten byggs automatiskt när du förhandsgranskar eller skriver. Den innehåller stilkort, utdrag och din uppgift.';
  }
}

/* ---------------------------------------------------------------- anslutning */

async function connect(silent) {
  const base = $('#baseUrl').value.trim();
  if (!base) {
    if (!silent) toast('Ange adressen till din LLM-server, t.ex. 127.0.0.1:8088.', 'warn');
    $('#baseUrl').focus();
    return;
  }
  const button = $('#connectBtn');
  button.disabled = true;
  setConnection('busy', 'Ansluter…');
  try {
    const data = await apiPost('/api/llm/probe', {
      base_url: base,
      api_key: S.llm.api_key || '',
    });
    S.conn = data;
    S.llm.base_url = data.base_url;
    S.llm.kind = data.kind;
    S.llm.context = Number(data.context) || 0;
    $('#baseUrl').value = data.base_url;

    applyModels(data);
    if (!S.llm.model && data.models.length) {
      S.llm.model = data.models[0];
      $('#modelSelect').value = S.llm.model;
    }

    const kind = KIND_LABEL[data.kind] || data.kind;
    const count = data.models.length;
    const ctxLabel = data.context ? ` · ${Math.round(data.context / 1024)}k ctx` : '';
    setConnection('ok', `${kind}${count ? ` · ${count} modell${count === 1 ? '' : 'er'}` : ''}${ctxLabel}`);
    const detail = [kind, data.base_url, data.detail, `${data.latency_ms} ms`]
      .filter(Boolean)
      .join(' · ');
    $('#serverDetail').textContent = detail;
    updateContextWarning();
    updateLabels();

    if (data.needs_key) {
      setConnection('warn', `${kind} · API-nyckel krävs`);
      if (!silent) {
        const advanced = $('#advancedGroup');
        if (advanced) advanced.open = true;
        $('#apiKey').focus();
        toast('Servern kräver en API-nyckel. Fyll i den under Avancerat och tryck Anslut igen.', 'warn');
      }
    } else if (!silent) {
      if (data.context && data.context < 4096) {
        toast(
          `Ansluten till ${kind}. Serverns kontext är bara ${formatNumber(data.context)} tokens — höj -c i llama.cpp för längre texter.`,
          'warn',
        );
      } else {
        toast(`Ansluten till ${kind}.`, 'success');
      }
    }
    persistSoon();
  } catch (error) {
    S.conn = null;
    S.llm.context = 0;
    updateContextWarning();
    setConnection('err', 'Ingen kontakt');
    $('#serverDetail').textContent = error.message;
    if (!silent) toast(error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

function applyModels(data) {
  const select = $('#modelSelect');
  const manual = $('#modelManual');
  select.innerHTML = '';

  if (!data.models || !data.models.length) {
    select.classList.add('hidden');
    manual.classList.remove('hidden');
    manual.value = S.llm.model || '';
    return;
  }

  select.classList.remove('hidden');
  manual.classList.add('hidden');

  if (S.llm.model && !data.models.includes(S.llm.model)) {
    // Modellen kommer från en annan server — välj serverns första istället.
    S.llm.model = data.models[0];
  }

  for (const name of data.models) {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    select.appendChild(option);
  }
  select.value = S.llm.model || data.models[0];
  if (select.value) S.llm.model = select.value;
  select.title = S.llm.model || '';
}

function setConnection(state, text) {
  const dot = $('#connDot');
  const cls = state === 'ok' ? 'ok'
    : state === 'err' ? 'err'
      : state === 'busy' ? 'busy'
        : state === 'warn' ? 'warn' : '';
  dot.className = `dot ${cls}`;
  $('#connText').textContent = text;
}

/* ---------------------------------------------------------------- generera */

async function generate(mode) {
  if (S.streaming) return;

  if (mode === 'new') {
    const hasScene = (S.brief.scene || '').trim().length >= 15;
    const hasParts = (S.brief.place || '').trim() && (S.brief.characters || '').trim();
    if (!hasScene && !hasParts) {
      toast('Beskriv scenen först — en rad om vad som händer räcker.', 'warn');
      $('#scene').focus();
      return;
    }
  }
  if (mode === 'continue' && !S.draft.trim()) {
    toast('Det finns ingen text att fortsätta på.', 'warn');
    return;
  }
  if (!S.llm.model && S.llm.kind === 'ollama') {
    toast('Välj en modell i listan uppe till höger.', 'warn');
    return;
  }
  if (S.conn && S.conn.needs_key && !S.llm.api_key) {
    const advanced = $('#advancedGroup');
    if (advanced) advanced.open = true;
    $('#apiKey').focus();
    toast('Servern kräver en API-nyckel. Fyll i den under Avancerat.', 'warn');
    return;
  }

  const override = $('#useEdited').checked ? $('#promptText').value.trim() : '';
  if (override && override.length < 40) {
    toast('Den redigerade prompten är för kort (minst 40 tecken).', 'warn');
    return;
  }

  if (S.editing) stopEditing();
  S.streaming = true;
  S.abort = new AbortController();
  S.autoScroll = true;
  S.lastGenerated = null;
  if (mode === 'new') {
    S.draft = '';
    S.savedPath = '';
  }
  setStreamingUI(true);
  switchTab('text');
  renderPaper();

  const payload = {
    brief: S.brief,
    llm: S.llm,
    save: S.save,
    mode,
    continuation: mode === 'continue' ? S.draft : '',
    prompt_override: override,
  };

  try {
    const response = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: S.abort.signal,
    });
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const data = await response.json();
        if (data && data.error) detail = data.error;
      } catch (error) { /* inte JSON */ }
      throw new Error(detail);
    }
    await readStream(response, handleStreamEvent);
  } catch (error) {
    if (error.name === 'AbortError') {
      toast('Avbruten. Det som hann skrivas finns kvar.', 'warn');
    } else {
      toast(error.message || 'Något gick fel vid genereringen.', 'error');
    }
  } finally {
    S.streaming = false;
    S.abort = null;
    setStreamingUI(false);
    renderPaper();
    persistSoon();
  }
}

function stopGeneration() {
  if (S.abort) S.abort.abort();
}

async function readStream(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let index;
      while ((index = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, index);
        buffer = buffer.slice(index + 2);
        for (const line of frame.split('\n')) {
          if (!line.startsWith('data:')) continue;
          const payload = line.slice(5).trim();
          if (!payload) continue;
          let event;
          try { event = JSON.parse(payload); } catch (error) { continue; }
          onEvent(event);
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}

function handleStreamEvent(event) {
  if (event.type === 'meta') {
    S.prompt = event.prompt || '';
    S.promptStats = event.stats || null;
    S.hitsStale = true;
    S.hitsCount = event.hits || 0;
    if (event.context) {
      S.llm.context = event.context;
      updateContextWarning();
    }
    $('#promptText').value = S.prompt;
    $('#promptStats').textContent = promptStatText(S.promptStats);
    $('#hitCount').textContent = event.hits || '';
    $('#hitCount').style.display = event.hits ? '' : 'none';
    S.promptDirty = false;
    if (!event.override) $('#useEdited').checked = false;
    return;
  }
  if (event.type === 'delta') {
    S.draft += event.text || '';
    scheduleRender();
    return;
  }
  if (event.type === 'warning') {
    toast(event.message, 'warn');
    return;
  }
  if (event.type === 'error') {
    throw new Error(event.message || 'Modellen svarade inte.');
  }
  if (event.type === 'done') {
    if (event.full_text) S.draft = event.full_text;
    S.lastGenerated = {
      words: event.words,
      seconds: event.seconds,
      saved: event.saved || null,
      title: event.title || S.brief.title || '',
      category: event.category || S.brief.category || '',
      repetition: Boolean(event.repetition),
    };
    if (event.saved && event.saved.path) {
      S.savedPath = event.saved.path;
      toast('Novellen är sparad.', 'success', event.saved.path);
    }
    refreshHistory();
    renderPaper();
  }
}

function promptStatText(stats) {
  if (!stats) return '';
  const tokens = stats.estimated_tokens ? ` · ~${formatNumber(stats.estimated_tokens)} tokens` : '';
  return `${formatNumber(stats.characters)} tecken${tokens}`;
}

function setStreamingUI(on) {
  $('#streamBadge').classList.toggle('hidden', !on);
  $('#stopBtn').classList.toggle('hidden', !on);
  $('#generateBtn').disabled = on;
  $('#continueBtn').disabled = on || !S.draft.trim();
  $('#saveBtn').disabled = on;
  $('#editBtn').disabled = on;
  $('#copyBtn').disabled = on;
  $('#downloadBtn').disabled = on;
  $('#clearBtn').disabled = on;
  $('#generateBtn').innerHTML = on
    ? 'Skriver…'
    : 'Skriv novell <kbd>Ctrl ↵</kbd>';
}

function scheduleRender() {
  if (S.renderQueued) return;
  S.renderQueued = true;
  requestAnimationFrame(() => {
    S.renderQueued = false;
    renderPaper();
  });
}

/* ---------------------------------------------------------------- papper */

function renderPaper() {
  const text = S.draft || '';
  const hasText = text.trim().length > 0;

  $('#emptyState').classList.toggle('hidden', hasText);
  $('#paperHead').classList.toggle('hidden', !hasText);

  if (hasText) {
    const title = (S.brief.title || '').trim()
      || (S.lastGenerated && S.lastGenerated.title)
      || 'Utkast';
    $('#paperTitle').textContent = title;

    const meta = [];
    if (S.lastGenerated) {
      if (S.lastGenerated.words) meta.push(`${formatNumber(S.lastGenerated.words)} ord`);
      if (S.lastGenerated.seconds) meta.push(`${S.lastGenerated.seconds} s`);
      if (S.lastGenerated.repetition) meta.push('stoppad före upprepning');
    } else {
      meta.push(`${formatNumber(countWords(text))} ord`);
    }
    if (S.llm.model) meta.push(S.llm.model);
    const category = (S.brief.category || '').trim();
    if (category) {
      const found = (S.boot.categories || []).find((item) => item.key === category);
      meta.push(found ? found.label : category);
    }
    $('#paperMeta').textContent = meta.filter(Boolean).join(' · ');
  }

  const prose = $('#prose');
  prose.classList.toggle('streaming', Boolean(S.streaming));
  if (hasText) {
    prose.innerHTML = proseToHtml(text);
  } else {
    prose.innerHTML = '';
  }

  $('#wordBadge').textContent = `${formatNumber(countWords(text))} ord`;
  $('#continueBtn').disabled = S.streaming || !hasText;
  if (hasText && S.streaming) scrollToBottom();
}

function updateWordBadge() {
  $('#wordBadge').textContent = `${formatNumber(countWords(S.draft))} ord`;
}

function toggleEditing() {
  if (S.streaming) {
    toast('Vänta tills texten är klar innan du redigerar.', 'warn');
    return;
  }
  if (S.editing) {
    stopEditing();
    renderPaper();
    toast('Redigeringen är klar.', 'info');
    return;
  }
  if (!S.draft.trim()) {
    toast('Det finns ingen text att redigera.', 'warn');
    return;
  }
  S.editing = true;
  const prose = $('#prose');
  prose.contentEditable = 'true';
  prose.classList.add('editing');
  prose.focus();
  $('#editBtn').textContent = 'Klar';
  toast('Redigera direkt i papperet. Tryck Klar när du är nöjd.', 'info');
}

function stopEditing() {
  if (!S.editing) return;
  S.editing = false;
  const prose = $('#prose');
  S.draft = prose.innerText.replace(/\u00a0/g, ' ').trim();
  prose.contentEditable = 'false';
  prose.classList.remove('editing');
  $('#editBtn').textContent = 'Redigera';
  updateWordBadge();
}

function proseToHtml(text) {
  const clean = String(text).replace(/\r\n/g, '\n');
  return clean
    .split(/\n{2,}/)
    .map((block) => {
      const trimmed = block.trim();
      if (!trimmed) return '';
      if (/^#{1,3}\s+/.test(trimmed)) {
        return `<h3>${inline(trimmed.replace(/^#{1,3}\s+/, ''))}</h3>`;
      }
      return `<p>${inline(trimmed)}</p>`;
    })
    .join('');
}

function inline(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*(?!\s)([^*]+?)\*/g, '$1<em>$2</em>')
    .replace(/\n/g, '<br>');
}

function scrollToBottom() {
  if (!S.autoScroll) return;
  const body = $('.work-body');
  if (body) body.scrollTop = body.scrollHeight;
}

/* ---------------------------------------------------------------- flikar */

function switchTab(name) {
  $$('.tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.tab === name));
  $('#paneText').classList.toggle('hidden', name !== 'text');
  $('#panePrompt').classList.toggle('hidden', name !== 'prompt');
  $('#paneRag').classList.toggle('hidden', name !== 'rag');

  if (name === 'prompt' && S.promptDirty && !S.streaming && !$('#useEdited').checked) {
    refreshPrompt(false);
  }
  if (name === 'rag' && S.hitsStale && !S.streaming) {
    refreshPrompt(false);
  }
  const body = $('.work-body');
  if (body) body.scrollTop = 0;
}

/* ---------------------------------------------------------------- prompt & RAG */

async function refreshPrompt(force) {
  if (S.streaming) return;
  if (force && $('#useEdited').checked) {
    $('#useEdited').checked = false;
  }
  const seq = ++S.promptSeq;
  try {
    const data = await apiPost('/api/prompt', {
      brief: S.brief,
      mode: 'new',
      continuation: '',
    });
    if (seq !== S.promptSeq) return;
    S.hits = data.hits || [];
    S.hitsStale = false;
    S.hitsCount = S.hits.length;
    S.prompt = data.prompt || '';
    S.promptStats = data.stats || null;
    $('#promptText').value = S.prompt;
    $('#promptStats').textContent = promptStatText(S.promptStats);
    $('#hitCount').textContent = S.hits.length ? String(S.hits.length) : '';
    $('#hitCount').style.display = S.hits.length ? '' : 'none';
    $('#ragNote').textContent = data.note || '';
    S.promptDirty = false;
    renderHits();
    $('#useEdited').checked = false;
    updatePromptPlaceholder();
  } catch (error) {
    if (seq === S.promptSeq) toast(error.message, 'error');
  }
}

function renderHits() {
  const wrap = $('#hitList');
  wrap.innerHTML = '';
  if (!S.hits.length) {
    const empty = document.createElement('div');
    empty.className = 'hit-empty';
    empty.textContent = S.brief.k === 0
      ? 'Stilprover är avstängda (antal = 0). Modellen får bara stilkortet.'
      : 'Inga utdrag hittades. Prova konkreta ord eller ett annat kategori filter.';
    wrap.appendChild(empty);
    return;
  }

  const excluded = new Set((S.brief.exclude_ids || []).map(Number));
  for (const hit of S.hits) {
    const article = document.createElement('article');
    article.className = 'hit' + (excluded.has(Number(hit.id)) ? ' excluded' : '');
    article.dataset.id = String(hit.id);

    const head = document.createElement('div');
    head.className = 'hit-head';

    const title = document.createElement('h3');
    title.textContent = hit.title || 'Utan titel';
    head.appendChild(title);

    const meta = document.createElement('span');
    meta.className = 'hit-meta';
    const rating = hit.rating ? `${Number(hit.rating).toFixed(1)}★` : '';
    meta.textContent = [hit.category, rating, hit.score ? `BM25 ${hit.score}` : '']
      .filter(Boolean)
      .join(' · ');
    head.appendChild(meta);

    const grow = document.createElement('span');
    grow.className = 'grow';
    head.appendChild(grow);

    const label = document.createElement('label');
    label.className = 'hit-toggle';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = !excluded.has(Number(hit.id));
    checkbox.addEventListener('change', () => toggleHit(hit.id, checkbox.checked));
    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(' använd'));
    head.appendChild(label);

    article.appendChild(head);

    const details = document.createElement('details');
    const summary = document.createElement('summary');
    const words = countWords(hit.text);
    summary.textContent = `Visa utdraget (${formatNumber(words)} ord)`;
    details.appendChild(summary);
    const paragraph = document.createElement('p');
    paragraph.textContent = hit.text || '';
    details.appendChild(paragraph);
    article.appendChild(details);

    wrap.appendChild(article);
  }
}

function toggleHit(id, include) {
  const set = new Set((S.brief.exclude_ids || []).map(Number));
  if (include) set.delete(Number(id));
  else set.add(Number(id));
  S.brief.exclude_ids = Array.from(set);
  S.promptDirty = true;
  const article = $(`.hit[data-id="${id}"]`);
  if (article) article.classList.toggle('excluded', !include);
  if (!$('#useEdited').checked) refreshPrompt(false);
  persistSoon();
}

async function doRagSearch() {
  S.brief.search_query = $('#searchQuery').value.trim();
  S.promptDirty = true;
  await refreshPrompt(true);
  switchTab('rag');
  if (S.hits.length) {
    toast(`${S.hits.length} stilprov hittade.`, 'info');
  }
}

/* ---------------------------------------------------------------- spara */

async function saveNow() {
  if (S.streaming) {
    toast('Vänta tills texten är klar — eller tryck Stopp först.', 'warn');
    return;
  }
  if (!S.draft.trim()) {
    toast('Det finns ingen text att spara.', 'warn');
    return;
  }
  try {
    const data = await apiPost('/api/save', {
      text: S.draft,
      title: S.brief.title || '',
      folder: S.save.folder,
      filename: S.save.filename,
      brief: S.brief,
      llm: S.llm,
      hits: S.hitsCount,
    });
    S.savedPath = data.path;
    toast('Novellen sparad.', 'success', data.path);
    refreshHistory();
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function copyDraft() {
  await copyText(S.draft, 'Texten kopierad.');
}

async function copyText(text, message) {
  if (!text) {
    toast('Det finns inget att kopiera.', 'warn');
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    toast(message, 'success');
  } catch (error) {
    const area = document.createElement('textarea');
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    area.remove();
    toast(message, 'success');
  }
}

function downloadDraft() {
  if (S.streaming) {
    toast('Vänta tills texten är klar.', 'warn');
    return;
  }
  if (!S.draft.trim()) {
    toast('Det finns ingen text att ladda ner.', 'warn');
    return;
  }
  const name = S.save.filename || `${(S.brief.title || 'novell').replace(/[^\wåäöÅÄÖ\- ]/g, '')}.md`;
  const blob = new Blob([S.draft], { type: 'text/markdown;charset=utf-8' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = name.endsWith('.md') ? name : `${name}.md`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 4000);
}

function clearDraft() {
  if (S.streaming) return;
  if (S.editing) stopEditing();
  if (!S.draft.trim()) return;
  if (!window.confirm('Töm textrutan? Det som inte sparats försvinner.')) return;
  S.draft = '';
  S.lastGenerated = null;
  S.savedPath = '';
  renderPaper();
  toast('Textrutan är tom.', 'info');
}

async function revealPath(path) {
  const target = (path || '').trim();
  if (!target) {
    toast('Välj en mapp först.', 'warn');
    return;
  }
  try {
    await apiPost('/api/fs/reveal', { path: target });
  } catch (error) {
    toast(error.message, 'error');
  }
}

/* ---------------------------------------------------------------- historik */

async function openLibrary() {
  $('#library').classList.remove('hidden');
  await refreshHistory();
}

async function refreshHistory() {
  try {
    const data = await apiGet('/api/history');
    S.history = data.items || [];
    if (!$('#library').classList.contains('hidden')) renderLibrary();
  } catch (error) {
    /* historiken är inte kritisk */
  }
}

function renderLibrary() {
  const list = $('#libraryList');
  list.innerHTML = '';
  $('#librarySub').textContent = S.history.length
    ? `${S.history.length} sparade texter`
    : 'Sparade noveller';
  $('#libraryEmpty').classList.toggle('hidden', S.history.length > 0);

  for (const entry of S.history) {
    const item = document.createElement('div');
    item.className = 'lib-item';
    item.dataset.id = entry.id;

    const main = document.createElement('div');
    main.className = 'lib-main';
    const title = document.createElement('h3');
    title.textContent = entry.title || 'Utan titel';
    const meta = document.createElement('p');
    meta.textContent = [
      svTime(entry.created),
      `${formatNumber(entry.words)} ord`,
      entry.category || '',
    ].filter(Boolean).join(' · ');
    main.appendChild(title);
    main.appendChild(meta);

    const actions = document.createElement('div');
    actions.className = 'lib-actions';
    const reveal = document.createElement('button');
    reveal.className = 'btn ghost';
    reveal.dataset.action = 'reveal';
    reveal.textContent = 'Mapp';
    reveal.title = 'Visa i Utforskaren';
    const remove = document.createElement('button');
    remove.className = 'btn ghost';
    remove.dataset.action = 'delete';
    remove.textContent = 'Ta bort';
    remove.title = 'Ta bort posten (filen ligger kvar)';
    actions.appendChild(reveal);
    actions.appendChild(remove);

    item.appendChild(main);
    item.appendChild(actions);
    list.appendChild(item);
  }
}

async function onLibraryClick(event) {
  const item = event.target.closest('.lib-item');
  if (!item) return;
  const action = event.target.closest('[data-action]');
  if (action) {
    event.stopPropagation();
    const entry = S.history.find((row) => row.id === item.dataset.id);
    if (!entry) return;
    if (action.dataset.action === 'reveal') {
      revealPath(entry.folder || entry.path);
    } else if (action.dataset.action === 'delete') {
      if (!window.confirm('Ta bort posten ur biblioteket? Filen ligger kvar på disken.')) return;
      try {
        await apiPost('/api/history/delete', { id: entry.id });
        await refreshHistory();
        renderLibrary();
      } catch (error) {
        toast(error.message, 'error');
      }
    }
    return;
  }
  await openHistoryItem(item.dataset.id);
}

async function openHistoryItem(id) {
  if (S.streaming) {
    toast('Avbryt eller vänta tills texten är klar innan du läser in en annan.', 'warn');
    return;
  }
  try {
    const data = await apiGet(`/api/history/item?id=${encodeURIComponent(id)}`);
    const entry = data.entry || {};
    if (S.editing) stopEditing();
    S.draft = cleanNovelText(data.text || '', entry.title || '');
    S.lastGenerated = {
      words: entry.words,
      seconds: null,
      title: entry.title || '',
      category: entry.category || '',
    };
    if (entry.title) {
      S.brief.title = entry.title;
      $('#title').value = entry.title;
    }
    if (entry.brief && typeof entry.brief === 'object') {
      const merged = { ...S.brief, ...entry.brief };
      merged.title = entry.title || merged.title;
      S.brief = merged;
      syncUI();
      renderWordChips();
      updateLabels();
      updatePathPreview();
    }
    $('#library').classList.add('hidden');
    renderPaper();
    switchTab('text');
    toast('Texten inläst.', 'info', entry.path || '');
  } catch (error) {
    toast(error.message, 'error');
  }
}

function cleanNovelText(text, title) {
  let value = String(text || '').replace(/\r\n/g, '\n');
  if (value.startsWith('---\n')) {
    const end = value.indexOf('\n---', 4);
    if (end >= 0) value = value.slice(end + 4).replace(/^\n+/, '');
  }
  const lines = value.split('\n');
  if (lines.length && /^#\s+/.test(lines[0])) {
    const heading = lines[0].replace(/^#\s+/, '').trim();
    if (!title || heading === title || heading.toLowerCase() === title.toLowerCase()) {
      lines.shift();
      while (lines.length && !lines[0].trim()) lines.shift();
    }
  }
  return lines.join('\n').trim();
}

/* ---------------------------------------------------------------- mappar */

async function openFolder(start) {
  $('#folderModal').classList.remove('hidden');
  await loadFolder(start || S.save.folder || '');
}

function closeFolder() {
  $('#folderModal').classList.add('hidden');
}

async function loadFolder(path) {
  try {
    const data = await apiGet(`/api/fs/list?path=${encodeURIComponent(path || '')}`);
    S.folderDir = data.path;
    S.folderPath = data.path;
    $('#folderPath').value = data.path;
    $('#folderChosen').textContent = data.path;
    renderFolderPlaces(data);
    renderFolderList(data);
  } catch (error) {
    toast(error.message, 'error');
  }
}

function renderFolderPlaces(data) {
  const wrap = $('#folderPlaces');
  wrap.innerHTML = '';

  const placesHead = document.createElement('div');
  placesHead.className = 'head';
  placesHead.textContent = 'Snabbplatser';
  wrap.appendChild(placesHead);

  for (const place of data.places || []) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'place';
    button.dataset.path = place.path;
    button.textContent = place.label;
    button.title = place.path;
    wrap.appendChild(button);
  }

  const drivesHead = document.createElement('div');
  drivesHead.className = 'head';
  drivesHead.textContent = 'Den här datorn';
  wrap.appendChild(drivesHead);

  for (const drive of data.drives || []) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'place drive';
    button.dataset.path = drive.path;
    button.textContent = drive.label;
    button.title = drive.path;
    wrap.appendChild(button);
  }
}

function renderFolderList(data) {
  const list = $('#folderList');
  list.innerHTML = '';

  if (data.parent) {
    const up = document.createElement('button');
    up.type = 'button';
    up.className = 'folder-row';
    up.dataset.path = data.parent;
    up.innerHTML = '<span class="ico">↑</span> ..';
    list.appendChild(up);
  }

  if (!data.dirs || !data.dirs.length) {
    const empty = document.createElement('div');
    empty.className = 'hit-empty';
    empty.textContent = 'Inga undermappar här. Välj den här mappen eller skapa en ny.';
    list.appendChild(empty);
    return;
  }

  for (const dir of data.dirs) {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'folder-row' + (dir.hidden ? ' hidden-dir' : '');
    row.dataset.path = dir.path;
    row.innerHTML = `<span class="ico">▸</span> ${escapeHtml(dir.name)}`;
    list.appendChild(row);
  }
}

async function chooseFolder() {
  if (!S.folderDir) return;
  S.save.folder = S.folderDir;
  $('#folder').value = S.folderDir;
  updatePathPreview();
  persistSoon();
  closeFolder();
  toast('Novellerna sparas i den valda mappen.', 'success', S.folderDir);
}

async function createFolder() {
  const name = $('#folderNewName').value.trim();
  if (!name) {
    toast('Ge mappen ett namn.', 'warn');
    return;
  }
  try {
    await apiPost('/api/fs/mkdir', { parent: S.folderDir, name });
    $('#folderNewName').value = '';
    await loadFolder(S.folderDir);
    toast('Mappen är skapad.', 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}

/* ---------------------------------------------------------------- exempel */

function applyExample(key) {
  const example = EXAMPLES[key];
  if (!example) return;
  Object.assign(S.brief, example);
  syncUI();
  renderWordChips();
  updateLabels();
  updatePathPreview();
  persistSoon();
  changed();
  $('#scene').focus();
  toast('Exemplet är ifyllt — ändra fritt.', 'info');
}

/* ---------------------------------------------------------------- 18+ */

function checkGate() {
  const accepted = localStorage.getItem('novellstudion-adult') === '1';
  $('#gate').classList.toggle('hidden', accepted);
}

/* ---------------------------------------------------------------- spara läge */

function persistSoon() {
  clearTimeout(S.stateTimer);
  S.stateTimer = setTimeout(persistState, 800);
}

async function persistState() {
  try {
    const llm = { ...S.llm };
    if (!llm.remember_key) llm.api_key = '';
    llm.context = 0;
    await apiPost('/api/state', {
      brief: S.brief,
      llm,
      save: S.save,
    });
  } catch (error) {
    /* tyst — inställningarna är inte kritiska */
  }
}

/* ---------------------------------------------------------------- tangenter */

function onKeydown(event) {
  const mod = event.ctrlKey || event.metaKey;
  if (mod && event.key === 'Enter') {
    event.preventDefault();
    generate('new');
    return;
  }
  if (mod && event.key.toLowerCase() === 's') {
    event.preventDefault();
    saveNow();
    return;
  }
  if (event.key === 'Escape') {
    $('#library').classList.add('hidden');
    $('#folderModal').classList.add('hidden');
    $('#helpModal').classList.add('hidden');
  }
  if (event.key === '?' && !event.ctrlKey && !event.metaKey && event.target === document.body) {
    $('#helpModal').classList.remove('hidden');
  }
}
