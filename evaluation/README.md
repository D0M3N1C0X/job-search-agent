# Labelled postings

`postings.json` holds 130 job postings, written for this benchmark, each labelled with what a person reading it
for the example candidate (`profile.example/`) would do: **apply**, **maybe** or **skip**, the rule that ends the
conversation where there is one (`gate`), the track it should be sent on, and one line saying why.

`python3 -m jsa evaluate` scores them and prints where the scorer disagrees with the label.

## Two sets, and why

- **development** (100 postings): written in two rounds and used to find and fix the scorer's mistakes. A rule
  that scores these well has been fitted to them, so their figures flatter.
- **held-out** (30 postings): written after the last change to the rules and scored once. Nothing in the scorer
  or the tracks was changed afterwards to make any of them come out right. These are the figures to quote.

When the scorer changes again, the held-out set becomes development and a new held-out set is written before
the next figures are published. A held-out set that has been tuned on is just more development data.

## What the labels are and are not

- They are one person's judgement for one profile: an HR advisor with three years of experience, English at C1,
  Dutch at B1, native Spanish, open to relocating in Europe. Another candidate would label some differently.
- The postings are synthetic, written to sound like real ones and to include the cases that broke the scorer
  before: a language named but not required, a country written in its own language, a company's age read as
  years of experience. They are not a sample of the market, so the percentages say how the rules behave on
  these cases, not how often the scorer is right on a real week of postings.
- For that, `jsa evaluate --mine` compares the scorer with your own decisions: what you prepared or sent against
  what you pressed skip on.
