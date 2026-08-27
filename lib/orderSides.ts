/**
 * The two sides of a transaction, and the only place in the interface they are written.
 *
 * AEGIS-Market never recommends an action. That prohibition is absolute, and it is checked
 * by a scan over every file in `app/`, `components/` and `lib/` — so the words BUY and
 * SELL cannot simply appear wherever a component finds them convenient.
 *
 * But an order ticket has to name its own sides. The distinction the policy turns on is
 * not the word, it is who is speaking: a side selector records what the *user* chose, and
 * a recommendation is the *system* saying what someone should do. The first is a record of
 * an instruction; the second is advice, and this product gives none.
 *
 * Making that distinction textual — allowing the word on some pages and not others — is
 * how a hole gets in: strip the token before scanning and `Signal: BUY` passes, which is
 * exactly the thing the policy forbids. So the distinction is structural instead. The
 * vocabulary lives here, in a file named for what it is, containing no other copy; every
 * other file imports it and never writes the words. A component that types `'BUY'` fails
 * the scan, wherever it is.
 *
 * `docs/NON_ADVISORY.md` is the policy; `tests/unit/test_non_advisory.py` enforces it.
 */

/** The sides a user may choose. Not a ranking, not a suggestion, not an output. */
export const ORDER_SIDES = ['BUY', 'SELL'] as const;

export type OrderSide = (typeof ORDER_SIDES)[number];

/** The side a fresh ticket opens on. A starting position for a form, nothing more. */
export const DEFAULT_ORDER_SIDE: OrderSide = ORDER_SIDES[0];

/** How a side is labelled to a reader: the user's instruction, said back to them. */
export function sideLabel(side: string): string {
  return String(side).toUpperCase();
}
