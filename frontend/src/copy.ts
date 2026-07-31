/**
 * Human wording for everything the backend calls by its internal name.
 *
 * One place on purpose. When a status or an action lives inline in a component,
 * the next value the backend adds leaks into the screen raw (`running_tools`,
 * `extract_now`) and nobody notices. Here an unknown value falls back to a
 * readable phrase instead of a keyword.
 */

export type Tone = 'neutral' | 'busy' | 'good' | 'warn' | 'bad' | 'attention';

interface Label {
  text: string;
  tone: Tone;
}

/** Chat-level state: what the whole research session is doing right now. */
const SESSION_STATE: Record<string, Label> = {
  active: { text: 'Ready', tone: 'neutral' },
  running_tools: { text: 'Visiting sites', tone: 'busy' },
  comparing: { text: 'Comparing sites', tone: 'busy' },
  completed: { text: 'Done', tone: 'good' },
  failed: { text: 'Stopped early', tone: 'bad' },
};

/** Per-site state. Deliberately says what happened, not what the code called it. */
const SITE_STATE: Record<string, Label> = {
  running: { text: 'Reading the site', tone: 'busy' },
  waiting_user: { text: 'Waiting for you', tone: 'attention' },
  completed: { text: 'Done', tone: 'good' },
  partial: { text: 'Partly done', tone: 'warn' },
  not_found: { text: 'Nothing found', tone: 'warn' },
  blocked: { text: 'Site blocked us', tone: 'warn' },
  canceled: { text: 'Stopped', tone: 'neutral' },
  failed: { text: "Couldn't read it", tone: 'bad' },
};

export const sessionState = (status: string): Label =>
  SESSION_STATE[status] ?? { text: humanizeKey(status), tone: 'neutral' };

export const siteState = (status: string): Label =>
  SITE_STATE[status] ?? { text: humanizeKey(status), tone: 'neutral' };

/** What the agent was after on a site — derived from the task, shown as intent. */
const GOAL: Record<string, string> = {
  content_search: 'Looking for an article',
  design_audit: 'Looking at the design',
  contact: 'Looking for contact details',
  contact_legal: 'Looking for legal contacts',
  pricing: 'Looking at prices',
  about: 'Reading about the company',
  careers: 'Looking at open roles',
  docs: 'Reading the documentation',
  commercial: 'Looking at the offer',
  blog: 'Reading the blog',
  site_map: 'Mapping the site',
  generic: 'General research',
};

export const goalLabel = (intent: string): string => GOAL[intent] ?? humanizeKey(intent);

/**
 * One step of the agent's work, in plain words.
 *
 * `action` wins over `state`: the action is what actually happened on the page,
 * while the state is the stage of the loop. A step with no action is a stage.
 */
const ACTION_STEP: Record<string, string> = {
  navigate: 'Opened a page',
  click: 'Clicked something on the page',
  fill: 'Typed into a field',
  fill_form: 'Filled in the form',
  extract_now: 'Pulled the answer from this page',
  stop: 'Decided it had enough',
};

const STAGE_STEP: Record<string, string> = {
  OBSERVE: 'Read the page',
  DECIDE: 'Picked the next move',
  ACT: 'Acted on the page',
  VISION_BATCH: 'Looked at the screenshots',
  SYNTHESIZE: 'Wrote up the findings',
  DONE: 'Finished',
};

export const stepLabel = (step: { state: string; action: string }): string =>
  ACTION_STEP[step.action] ?? STAGE_STEP[step.state] ?? humanizeKey(step.state);

/** Comparison rubric — the yardstick, said out loud. */
const RUBRIC: Record<string, string> = {
  content_completeness: 'how complete the content is',
  design_diff: 'how the designs differ',
  generic_merge: 'overall quality',
};

export const rubricLabel = (rubric: string): string =>
  RUBRIC[rubric] ?? humanizeKey(rubric).toLowerCase();

/** Pause cards: why the agent stopped and what the human has to do. */
export const pauseCopy = (
  kind: string,
  action: string | null | undefined,
): { title: string; body: string; button: string } => {
  if (kind === 'handoff') {
    return {
      title: 'Your turn to press it',
      body: `This step can't be undone${action ? `: ${action}` : ''}, so the agent never presses it. Do it yourself in the browser window that just opened — or skip it if you changed your mind — then come back here.`,
      button: 'Done — carry on',
    };
  }
  if (kind === 'confirm_submit') {
    return {
      title: 'Send this form?',
      body: `The agent wants to submit ${action ? `“${action}”` : 'the form on this page'}. Take a look in the open browser window and confirm — then the agent will press it.`,
      button: 'Yes, send it',
    };
  }
  if (kind === 'login_wall') {
    return {
      title: 'This site wants a login',
      body: 'A browser window is open — sign in there yourself. Your password stays with you: the agent never sees or stores it.',
      button: "I'm in — carry on",
    };
  }
  return {
    title: 'The site wants to check you',
    body: 'A browser window is open with an anti-bot check. Pass it there, then come back — the agent picks up where it left off.',
    button: 'Passed it — carry on',
  };
};

/** Errors: the user gets a sentence, the raw text stays available for debugging. */
const ERROR_HINT: [RegExp, string][] = [
  [/run_in_progress/i, 'Another research run is still going. Wait for it, or stop it first.'],
  [/session_busy/i, 'This chat is still working. Wait for it to finish, or stop it.'],
  [/not found/i, 'That chat is gone — it may have been deleted.'],
  [
    /failed to fetch|networkerror|load failed/i,
    "Can't reach the agent on this machine. Is it still running?",
  ],
  [/no urls/i, 'No web addresses in that message — paste at least one link.'],
  [/robots/i, "That site's rules ask us not to crawl it, so the agent stopped."],
  [/timeout|timed out/i, 'The site took too long to answer.'],
];

export const errorText = (raw: unknown): string => {
  const text = String(raw ?? '').replace(/^Error:\s*/, '');
  for (const [pattern, hint] of ERROR_HINT) if (pattern.test(text)) return hint;
  return text || 'Something went wrong.';
};

/** Counters — as a phrase, not `3/10`. */
export const pagesRead = (visited: number, max: number): string =>
  `${visited} of ${max} ${max === 1 ? 'page' : 'pages'} read`;

export const siteCount = (n: number): string => `${n} ${n === 1 ? 'site' : 'sites'}`;

export const wordCount = (n: number): string => `about ${n.toLocaleString('en-US')} words`;

/** `snake_case` or `CONST_CASE` → sentence case. Last line of defence: anything
 *  the backend or the model invents still reads like language, not like a key. */
export function humanizeKey(key: string): string {
  const words = key.replace(/[_-]+/g, ' ').trim().toLowerCase();
  if (!words) return '';
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Host without the noise — what a person recognises a site by. */
export function siteName(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, '');
  } catch {
    return url;
  }
}

export const relativeTime = (iso: string, now: number = Date.now()): string => {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return '';
  const mins = Math.round((now - then) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? 'yesterday' : `${days} days ago`;
};
