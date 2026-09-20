// TEMPORARY matchups list for /matchups.html — edit this file to swap/add bouts.
// Each side: { name, id, gender }. Leave id null (or omit) when the wrestler has no KentuckyMat profile yet —
// the name shows as plain text and the Compare button is disabled. Compare works only when BOTH sides have an id
// and the same gender (boys/girls career IDs overlap, so gender is always required with the id).
// `rank` is the rank printed on the source graphic (optional). `tag` is small text under the name (e.g. 'College').
window.MATCHUPS_TITLE = '2027 All Star Classic';
window.MATCHUPS_SUBTITLE = 'Tap a name for a profile, or Compare for head-to-head.';
window.MATCHUPS = [
  { a: { name: 'Spencer Moore', id: 'career_008940', gender: 'boys', tag: 'College' }, b: { name: 'Isaac Thornton', id: 'career_007965', gender: 'boys', tag: 'College' } },
  { a: { name: 'Peyton Vowels', id: 'career_001715', gender: 'boys', rank: 1 },     b: { name: 'Kalob Wise', id: 'career_001791', gender: 'boys', rank: 2 } },
  { a: { name: 'Jagger Irvin', id: 'career_002344', gender: 'boys', rank: 6 },      b: { name: 'Blake Luttrell', id: 'career_000833', gender: 'boys', rank: 3 } },
  { a: { name: 'Mason Gipson', id: 'career_002508', gender: 'boys', rank: 4 },      b: { name: 'Lane Griffin', id: 'career_001856', gender: 'boys', rank: 3 } },
  { a: { name: 'Cody Blevins', id: 'career_002440', gender: 'boys', rank: 2 },      b: { name: 'Talon Sanderlyn', id: 'career_000265', gender: 'boys', rank: 3 } },
  { a: { name: 'Ana Tierney', id: 'career_000847', gender: 'girls', rank: 2 },      b: { name: 'Juliette Ruiz', id: 'career_000032', gender: 'girls', rank: 1 } },
  { a: { name: 'Kayson White', id: 'career_001227', gender: 'boys', rank: 1 },      b: { name: 'Emory Dix', id: 'career_001498', gender: 'boys', rank: 3 } },
  { a: { name: 'Parker Wilkins', id: 'career_001219', gender: 'boys', rank: 4 },    b: { name: 'Mason Brooks', id: 'career_005108', gender: 'boys', rank: 7 } },
  { a: { name: 'Austin Goodpaster', id: 'career_001839', gender: 'boys', rank: 4 }, b: { name: 'Maxx Escaloni', id: 'career_005783', gender: 'boys', rank: 1 } },
  { a: { name: 'Asher Crisp', tag: 'Middle school' },                b: { name: 'Reign Gutterman', tag: 'Middle school' } },
  { a: { name: 'Peyton Brinkman', id: 'career_000669', gender: 'girls', rank: 2 },  b: { name: 'Payton Pomeroy', id: 'career_000232', gender: 'girls', rank: 1 } },
  { a: { name: 'Jackson Stoner', id: 'career_000646', gender: 'boys', rank: 2 },    b: { name: 'Mohamud Talasow', id: 'career_000827', gender: 'boys', rank: 4 } },
  { a: { name: 'Cullen White', id: 'career_000268', gender: 'boys', rank: 3 },      b: { name: 'Brock Fernandez', id: 'career_002652', gender: 'boys', rank: 3 } },
  { a: { name: 'JJ Mollett', id: 'career_001602', gender: 'boys', rank: 3 },        b: { name: 'Ayden Votaw', id: 'career_001810', gender: 'boys', rank: 5 } },
  { a: { name: 'Noah Crisp', id: 'career_002339', gender: 'boys', rank: 2 },        b: { name: 'Josh Tuttle', id: 'career_000839', gender: 'boys', rank: 4 } },
  { a: { name: 'Abel Dietz', tag: 'Middle school' },                 b: { name: 'Ashdon Yost', tag: 'Middle school' } },
  { a: { name: 'Kaygen Roberts', id: 'career_000278', gender: 'boys', rank: 1 },    b: { name: 'Santiago Gonzalez', id: 'career_001792', gender: 'boys', rank: 1 } }
];
