package apkeep.ndd;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.ants.jndd.diagram.AtomizedNDD;
import org.ants.jndd.diagram.NDD;
import org.ants.jndd.fave.FaveFields;

import apkeep.core.ChangeItem;
import apkeep.elements.Element;
import apkeep.rules.RewriteRule;
import common.Fields;

/**
 * NDD-APKeep's port predicate map: APKeep's atom layer replaced by NDD's
 * (APKEEP_INCREMENTAL_SCOPE.md §4, owner decision B).
 *
 * <p>BDD-APKeep keeps, per port, a set of global atomic predicates and splits
 * them through every element. NDD-APKeep keeps atoms PER FIELD (the NDD
 * library's {@link AtomizedNDD}) and, per port, a <em>molecule</em> -- an NDD
 * whose edge labels are sets of atoms. A change tuple (from, to, delta) is
 * applied as in the NDD paper (App. F.2): split the atoms delta cuts, then move
 * delta's atoms from {@code from}'s molecule to {@code to}'s.
 *
 * <p><b>Provenance.</b> Ported from the authors' reference APKeep(NDD)
 * ({@code application.wan.ndd.verifier.apkeep}, in-tree under ndd/):
 * <ul>
 * <li>{@link #applyCube} is {@code FieldNodeAP.update_ACL}'s per-cube body;
 *     {@link #applySingleField} is {@code FieldNodeAP.update_FW}'s, for a delta
 *     on one field leaving a molecule on that field alone;</li>
 * <li>{@link #split} is {@code NetworkNDDAP.split_ap_multi_field} with
 *     {@code SplitMap.split}: an atom's holders are tracked so a split
 *     rewrites only the molecules that hold it;</li>
 * <li>{@link #reatomize} is {@code NetworkNDDAP.UpdateFieldAP}: the reference
 *     never merges atoms, it re-atomizes every port predicate from scratch
 *     (every 1500 ACL rules and after a build). That is NDD-APKeep's merge.</li>
 * </ul>
 * FaVe's, and to be labelled so: the plain predicate kept beside each molecule
 * (the reference keeps one too, {@code ports_pred}, but only for
 * re-atomization -- here it is also what a footprint and the invariant check
 * read); removal, which needs nothing beyond moving a delta back (the element
 * computes the tuples); rewrites, kept as atomized new values ({@link
 * #addRewrite}) and applied by {@code exist} as in the paper's App. F.3; the
 * re-atomization schedule during updates; and several networks per JVM.
 *
 * <p><b>Several networks per JVM.</b> The atoms are process-global statics of
 * the NDD library, so a split made for one network cuts atoms other networks'
 * molecules hold (FaVe's from-zero oracle builds a twin beside the network
 * being updated). Every live map is registered, and {@link #split} and
 * {@link #reatomize} reach all of them.
 */
public final class NddPorts {

	/** A molecule and the plain predicate it stands for. A port of an
	 *  element, or the new value of a rewrite (a NAT rule's port). */
	static final class Holder {
		final String element;
		final String port;
		final boolean rewrite;
		AtomizedNDD mol;   // referenced
		int pred;          // referenced (plain NDD)
		int field = -1;    // rewrites only: the field written
		// Incremental atom bookkeeping (FAVE_CHANGES.md §15): the nodes of `mol`, each with
		// the number of edges -- and the holder's root reference -- that reach
		// it inside `mol`; and per field, how many distinct-node edge labels
		// carry each atom. An atom is in the molecule iff its count is > 0,
		// the set `AtomizedNDD.collectAtoms` computes by walking it.
		final IdentityHashMap<AtomizedNDD, Integer> refs = new IdentityHashMap<>();
		@SuppressWarnings("unchecked")
		final HashMap<Integer, Integer>[] atomCount = new HashMap[AtomizedNDD.getFieldNum() + 1];
		{ for (int f = 0; f < atomCount.length; f++) atomCount[f] = new HashMap<>(); }

		Holder(String element, String port, boolean rewrite, AtomizedNDD mol, int pred) {
			this.element = element;
			this.port = port;
			this.rewrite = rewrite;
			this.mol = mol;
			this.pred = pred;
		}
	}

	private static final List<NddPorts> LIVE = new ArrayList<>();

	// The reference's operation cache (FAVE_CHANGES.md §15): the authors' DPVerifierNDDAP
	// enables AtomizedNDD's `and` cache for the property check and disables it
	// for updates. Queries switch it on and keep it across queries; anything
	// that changes molecules switches it off and clears it first. (A garbage
	// collection clears it inside the library.)
	private static boolean queryCache = false;

	/** Queries: the `and` cache on, kept from the previous query. */
	public static void enterQueries() {
		if (!queryCache) {
			AtomizedNDD.enableCaches();
			queryCache = true;
		}
	}

	/** A change to molecules: the cache off and empty, as for the reference's updates. */
	public static void leaveQueries() {
		if (queryCache) {
			AtomizedNDD.disableCaches();
			AtomizedNDD.clearCaches();
			queryCache = false;
		}
	}

	/** Re-atomize after this many updates (the reference's MERGE_ACL_NUMBER). */
	public static int REATOMIZE_EVERY = 1500;

	private final Map<String, Map<String, Holder>> ports = new LinkedHashMap<>();
	private final Map<String, Map<String, Holder>> rewrites = new LinkedHashMap<>();
	/** SplitMap: per field, atom -> the holders whose molecule contains it. */
	private final Map<Integer, Set<Holder>>[] holders;
	private int sinceReatomize = 0;

	@SuppressWarnings("unchecked")
	public NddPorts() {
		FaveFields.ensure();
		holders = new HashMap[AtomizedNDD.getFieldNum() + 1];
		for (int f = 0; f < holders.length; f++) holders[f] = new HashMap<>();
		synchronized (LIVE) {
			LIVE.add(this);
		}
	}

	private boolean closed = false;

	/** Leave the registry and release every molecule and predicate. Once. */
	public void close() {
		if (closed) return;
		closed = true;
		synchronized (LIVE) {
			LIVE.remove(this);
		}
		for (Map<String, Holder> m : ports.values())
			for (Holder h : m.values()) release(h);
		for (Map<String, Holder> m : rewrites.values())
			for (Holder h : m.values()) release(h);
		ports.clear();
		rewrites.clear();
		for (Map<Integer, Set<Holder>> m : holders) m.clear();
	}

	private static void release(Holder h) {
		AtomizedNDD.deref(h.mol);
		NDD.deref(h.pred);
	}

	// ---- ports -----------------------------------------------------------

	public Set<String> ports(Element e) {
		Map<String, Holder> m = ports.get(e.getName());
		return m == null ? Collections.<String>emptySet() : m.keySet();
	}

	public void initPort(Element e, String port, boolean all) {
		leaveQueries();
		Map<String, Holder> m = ports.computeIfAbsent(e.getName(), k -> new LinkedHashMap<>());
		Holder old = m.get(port);
		if (old != null) {
			setMolecule(old, all ? AtomizedNDD.getAtomizedTrue() : AtomizedNDD.getAtomizedFalse());
			NDD.deref(old.pred);
			old.pred = all ? NDD.getTrue() : NDD.getFalse();
			return;
		}
		m.put(port, new Holder(e.getName(), port, false,
				all ? AtomizedNDD.getAtomizedTrue() : AtomizedNDD.getAtomizedFalse(),
				all ? NDD.getTrue() : NDD.getFalse()));
	}

	public void ensurePort(Element e, String port) {
		Map<String, Holder> m = ports.get(e.getName());
		if (m == null || !m.containsKey(port)) initPort(e, port, false);
	}

	public AtomizedNDD molecule(String element, String port) {
		Holder h = ports.get(element).get(port);
		return h.mol;
	}

	public int predicate(String element, String port) {
		return ports.get(element).get(port).pred;
	}

	/** The NDD field a rewrite writes. */
	public static int field(Fields f) {
		switch (f) {
		case dst_ip: return FaveFields.DST4;
		case src_ip: return FaveFields.SRC4;
		case vlan: return FaveFields.VLAN;
		default: throw new IllegalArgumentException("no NDD field for rewrite of " + f);
		}
	}

	/** Atomize the new value of a NAT rule's port, once per port: the atoms
	 *  of its field are split so the value is a union of them, and the
	 *  molecule is kept current by later splits like any port's. */
	public void addRewrite(Element e, String port, RewriteRule rule) {
		leaveQueries();
		Map<String, Holder> m = rewrites.computeIfAbsent(e.getName(), k -> new LinkedHashMap<>());
		if (m.containsKey(port)) return;
		int field = field(rule.getField());
		int value = rule.getNew_pkt_bdd();
		if (!NDD.isTerminal(value) && NDD.getField(value) != field) {
			throw new IllegalArgumentException("rewrite value of " + e.getName() + "." + port
					+ " is not on the field it writes");
		}
		Holder h = new Holder(e.getName(), port, true, AtomizedNDD.getAtomizedFalse(), NDD.ref(value));
		h.field = field;
		m.put(port, h);
		if (NDD.isTrue(value)) {
			setMolecule(h, AtomizedNDD.getAtomizedTrue());
			return;
		}
		if (NDD.isFalse(value)) return;
		// the value's atoms, splitting those it cuts (as update_FW does for delta)
		HashSet<Integer> atoms = new HashSet<>();
		HashMap<Integer, HashSet<Integer>> cut = new HashMap<>();
		AtomizedNDD.getAtomsToSplitSingleField(AtomizedNDD.getAtomizedTrue(),
				NDD.getEdgeLabel(value, 0), atoms, cut, field);
		splitOneField(cut, field);
		setMolecule(h, singleField(field, atoms));
	}

	/** (molecule of a NAT port's rule, field written, molecule of the value)
	 *  for every rewrite of one NAT element: port -> holder. */
	Map<String, Holder> rewritesOf(String element) {
		Map<String, Holder> m = rewrites.get(element);
		return m == null ? Collections.<String, Holder>emptyMap() : m;
	}

	// ---- updates -----------------------------------------------------------

	/**
	 * Apply one element's change tuples; returns the molecule of everything
	 * moved (referenced), which APKeep's per-update loop check starts from.
	 */
	public AtomizedNDD update(Element e, List<ChangeItem> changes) {
		leaveQueries();
		// What moved, held like a port while the tuples are applied: a split
		// made for a later tuple must reach the molecule of an earlier one.
		Holder acc = new Holder(e.getName(), "\u0000moved", false,
				AtomizedNDD.getAtomizedFalse(), NDD.getFalse());
		Map<String, Holder> m = ports.get(e.getName());
		for (ChangeItem item : changes) {
			Holder from = m.get(item.getFrom_port());
			Holder to = m.get(item.getTo_port());
			int delta = item.getDelta();
			// the plain predicates (FieldNodeAP.update_ACL keeps ports_pred too)
			int t1 = from.pred;
			from.pred = NDD.ref(NDD.diff(t1, delta));
			NDD.deref(t1);
			int t2 = to.pred;
			to.pred = NDD.ref(NDD.or(t2, delta));
			NDD.deref(t2);

			int field = singleFieldOf(delta);
			if (field >= 0 && onlyOn(from.mol, field)) {
				AtomizedNDD part = applySingleField(from, to, delta, field);
				setMolecule(acc, AtomizedNDD.or(acc.mol, part));
				AtomizedNDD.deref(part);
			} else {
				for (int[] cube : NDD.toArray(delta)) {
					AtomizedNDD part = applyCube(from, to, cube);
					setMolecule(acc, AtomizedNDD.or(acc.mol, part));
					AtomizedNDD.deref(part);
				}
			}
		}
		AtomizedNDD moved = AtomizedNDD.ref(acc.mol);
		setMolecule(acc, AtomizedNDD.getAtomizedFalse());   // unmapped again
		return moved;
	}

	/** The field of a predicate on one field only, or -1. */
	private static int singleFieldOf(int ndd) {
		if (NDD.isTerminal(ndd)) return -1;
		int field = NDD.getField(ndd);
		for (int k = 0; k < NDD.getEdgeCount(ndd); k++) {
			if (!NDD.isTrue(NDD.getEdgeTarget(ndd, k))) return -1;
		}
		return field;
	}

	/** True iff a molecule constrains no field but `field`. */
	private static boolean onlyOn(AtomizedNDD mol, int field) {
		if (mol.isTerminal()) return true;
		if (mol.getField() != field) return false;
		for (AtomizedNDD next : mol.getAtomizedEdges().keySet()) {
			if (!next.isTrue()) return false;
		}
		return true;
	}

	private static AtomizedNDD singleField(int field, Set<Integer> atoms) {
		if (atoms.isEmpty()) return AtomizedNDD.getAtomizedFalse();
		if (atoms.size() == AtomizedNDD.getAllAtoms(field).size()) return AtomizedNDD.getAtomizedTrue();
		HashMap<AtomizedNDD, HashSet<Integer>> edges = new HashMap<>();
		edges.put(AtomizedNDD.getAtomizedTrue(), new HashSet<>(atoms));
		return AtomizedNDD.mkAtomized(field, edges);
	}

	/** update_FW's body: delta on one field, `from` on that field alone. */
	private AtomizedNDD applySingleField(Holder from, Holder to, int delta, int field) {
		HashSet<Integer> deltaAtoms = new HashSet<>();
		HashMap<Integer, HashSet<Integer>> cut = new HashMap<>();
		AtomizedNDD.getAtomsToSplitSingleField(from.mol, NDD.getEdgeLabel(delta, 0), deltaAtoms, cut, field);
		splitOneField(cut, field);
		AtomizedNDD moved = AtomizedNDD.ref(singleField(field, deltaAtoms));
		move(from, to, moved);
		return moved;
	}

	/** update_ACL's per-cube body: delta's cube `cube` (one label per field). */
	private AtomizedNDD applyCube(Holder from, Holder to, int[] cube) {
		int n = AtomizedNDD.getFieldNum() + 1;
		ArrayList<HashSet<Integer>> deltaAtoms = new ArrayList<>();
		ArrayList<HashMap<Integer, HashSet<Integer>>> cut = new ArrayList<>();
		for (int f = 0; f < n; f++) {
			deltaAtoms.add(new HashSet<>());
			cut.add(new HashMap<>());
		}
		AtomizedNDD.getAtomsToSplitMultipleFields(from.mol, cube, deltaAtoms, cut, 0);
		split(cut);
		for (int f = 0; f < n; f++) {
			if (deltaAtoms.get(f).isEmpty()) {
				throw new IllegalStateException("a change tuple's cube found no atoms on field " + f
						+ " of its source port " + from.element + "." + from.port);
			}
		}
		AtomizedNDD moved = AtomizedNDD.getAtomizedTrue();
		for (int f = n - 1; f >= 0; f--) {
			HashMap<AtomizedNDD, HashSet<Integer>> edges = new HashMap<>();
			edges.put(moved, deltaAtoms.get(f));
			AtomizedNDD next = AtomizedNDD.ref(AtomizedNDD.mkAtomized(f, edges));
			AtomizedNDD.deref(moved);    // the new node holds its child
			moved = next;
		}
		move(from, to, moved);
		return moved;
	}

	private void move(Holder from, Holder to, AtomizedNDD moved) {
		setMolecule(from, AtomizedNDD.diff(from.mol, moved));
		setMolecule(to, AtomizedNDD.or(to.mol, moved));
	}

	/** Replace a holder's molecule (unreferenced `mol`), keeping the SplitMap. */
	private void setMolecule(Holder h, AtomizedNDD mol) {
		AtomizedNDD old = h.mol;
		AtomizedNDD.ref(mol);
		swapBookkeeping(h, old, mol);
		h.mol = mol;
		AtomizedNDD.deref(old);
	}

	/** Move a holder's bookkeeping from `old` to `mol` and the
	 *  SplitMap with it, visiting only the nodes `mol` adds and `old` drops:
	 *  the new root is counted first, so nodes both share never drop. */
	private void swapBookkeeping(Holder h, AtomizedNDD old, AtomizedNDD mol) {
		if (old == mol) return;
		HashMap<Integer, Boolean>[] before = new HashMap[h.atomCount.length];
		for (int f = 0; f < before.length; f++) before[f] = new HashMap<>();
		addRef(h, mol, before);
		delRef(h, old, before);
		for (int f = 0; f < before.length; f++) {
			for (Map.Entry<Integer, Boolean> e : before[f].entrySet()) {
				int atom = e.getKey();
				boolean now = h.atomCount[f].containsKey(atom);
				if (now == e.getValue()) continue;
				if (now) {
					holders[f].computeIfAbsent(atom, k -> Collections.newSetFromMap(new IdentityHashMap<>())).add(h);
				} else {
					Set<Holder> s = holders[f].get(atom);
					if (s != null) s.remove(h);
				}
			}
		}
	}

	private static void touch(Holder h, int f, int atom, HashMap<Integer, Boolean>[] before) {
		if (!before[f].containsKey(atom)) before[f].put(atom, h.atomCount[f].containsKey(atom));
	}

	private static void addRef(Holder h, AtomizedNDD n, HashMap<Integer, Boolean>[] before) {
		if (n.isTerminal()) return;
		Integer c = h.refs.get(n);
		if (c != null) { h.refs.put(n, c + 1); return; }
		h.refs.put(n, 1);
		int f = n.getField();
		for (Map.Entry<AtomizedNDD, HashSet<Integer>> e : n.getAtomizedEdges().entrySet()) {
			for (int atom : e.getValue()) {
				touch(h, f, atom, before);
				h.atomCount[f].merge(atom, 1, Integer::sum);
			}
			addRef(h, e.getKey(), before);
		}
	}

	private static void delRef(Holder h, AtomizedNDD n, HashMap<Integer, Boolean>[] before) {
		if (n.isTerminal()) return;
		int c = h.refs.get(n) - 1;
		if (c > 0) { h.refs.put(n, c); return; }
		h.refs.remove(n);
		int f = n.getField();
		for (Map.Entry<AtomizedNDD, HashSet<Integer>> e : n.getAtomizedEdges().entrySet()) {
			for (int atom : e.getValue()) {
				touch(h, f, atom, before);
				int k = h.atomCount[f].get(atom) - 1;
				if (k == 0) h.atomCount[f].remove(atom); else h.atomCount[f].put(atom, k);
			}
			delRef(h, e.getKey(), before);
		}
	}

	// ---- splits ------------------------------------------------------------

	private static void splitOneField(HashMap<Integer, HashSet<Integer>> cut, int field) {
		if (cut.isEmpty()) return;
		ArrayList<HashMap<Integer, HashSet<Integer>>> all = new ArrayList<>();
		for (int f = 0; f <= AtomizedNDD.getFieldNum(); f++) all.add(new HashMap<>());
		all.set(field, cut);
		split(all);
	}

	/** split_ap_multi_field + SplitMap.split, over every live map. */
	private static void split(ArrayList<HashMap<Integer, HashSet<Integer>>> cut) {
		boolean empty = true;
		for (HashMap<Integer, HashSet<Integer>> m : cut) if (!m.isEmpty()) empty = false;
		if (empty) return;
		for (int f = 0; f < cut.size(); f++) {
			for (Map.Entry<Integer, HashSet<Integer>> entry : cut.get(f).entrySet()) {
				AtomizedNDD.getAllAtoms(f).remove(entry.getKey());
				AtomizedNDD.getAllAtoms(f).addAll(entry.getValue());
				NDD.getBDDEngine().deref(entry.getKey());
			}
		}
		List<NddPorts> live;
		synchronized (LIVE) {
			live = new ArrayList<>(LIVE);
		}
		for (NddPorts p : live) p.splitHolders(cut);
	}

	private void splitHolders(ArrayList<HashMap<Integer, HashSet<Integer>>> cut) {
		Set<Holder> touched = Collections.newSetFromMap(new IdentityHashMap<>());
		for (int f = 0; f < cut.size(); f++) {
			for (int atom : cut.get(f).keySet()) {
				if (atom == 1) continue;
				Set<Holder> s = holders[f].get(atom);
				if (s != null) touched.addAll(s);
			}
		}
		for (Holder h : touched) {
			NDD.Pair<Boolean, AtomizedNDD> ret =
					AtomizedNDD.splitMultipleFieldsAtomsWithMultipleFieldsPredicate(cut, h.mol);
			if (ret.getKey()) {
				AtomizedNDD.ref(ret.getValue());
				AtomizedNDD old = h.mol;
				// The bookkeeping moves to the split molecule, and the
				// SplitMap with it -- the cut atom leaves, its parts arrive
				swapBookkeeping(h, old, ret.getValue());
				h.mol = ret.getValue();
				AtomizedNDD.deref(old);
			}
		}
		for (int f = 0; f < cut.size(); f++) {
			for (int atom : cut.get(f).keySet()) {
				Set<Holder> s = holders[f].get(atom);
				if (s != null && s.isEmpty()) holders[f].remove(atom);
			}
		}
	}

	// ---- garbage --------------------------------------------------------------

	private static long liveAfterCollect = 0;
	/** Collect when the atomized table has grown past twice what survived the
	 *  last collection (and past this floor). */
	public static long COLLECT_FLOOR = 50_000;
	/** Collections made (a test reads it). */
	public static long collections = 0;

	/**
	 * Collect the atomized node table if it has grown enough. The NDD library
	 * collects only when the table is full (8M nodes in FaVe's layout), and an
	 * NDD-APKeep molecule's nodes each carry atom sets of up to thousands of
	 * ids: dead molecules filled tens of GB first (wl_airtel1, wl_i2 faithful).
	 * Collecting removes every unreferenced node, so callers invoke this only
	 * where everything in use is referenced -- between updates and between
	 * queries.
	 */
	public static void maybeCollect() {
		long size = AtomizedNDD.tableSize();
		if (size > COLLECT_FLOOR && size > 2 * liveAfterCollect) {
			AtomizedNDD.collectGarbage();
			liveAfterCollect = AtomizedNDD.tableSize();
			collections++;
		}
	}

	// ---- merging: re-atomization -------------------------------------------

	/** Count one update; re-atomize every {@link #REATOMIZE_EVERY}. */
	public void countUpdate() {
		if (++sinceReatomize >= REATOMIZE_EVERY) reatomize();
	}

	/**
	 * NetworkNDDAP.UpdateFieldAP over every live map: atomize all their plain
	 * predicates afresh (the coarsest per-field partition they induce) and
	 * rebuild every molecule and the SplitMap. The NDD library leaves the
	 * previous atoms referenced; they are released here.
	 */
	public static void reatomize() {
		leaveQueries();
		List<NddPorts> live;
		synchronized (LIVE) {
			live = new ArrayList<>(LIVE);
		}
		HashSet<Integer> preds = new HashSet<>();
		for (NddPorts p : live) {
			p.sinceReatomize = 0;
			for (Holder h : p.allHolders()) preds.add(h.pred);
		}
		List<Integer> oldAtoms = new ArrayList<>();
		for (int f = 0; f <= AtomizedNDD.getFieldNum(); f++) oldAtoms.addAll(AtomizedNDD.getAllAtoms(f));
		HashMap<Integer, HashSet<Integer>[]> unused = new HashMap<>();
		HashMap<Integer, AtomizedNDD> mol = AtomizedNDD.atomization(preds, unused);
		for (NddPorts p : live) {
			for (Map<Integer, Set<Holder>> m : p.holders) m.clear();
			for (Holder h : p.allHolders()) {
				AtomizedNDD old = h.mol;
				h.mol = AtomizedNDD.getAtomizedFalse();
				h.refs.clear();
				for (HashMap<Integer, Integer> c : h.atomCount) c.clear();
				AtomizedNDD.deref(old);
				p.setMolecule(h, mol.get(h.pred));
			}
		}
		for (int atom : oldAtoms) {
			if (atom != 1) NDD.getBDDEngine().deref(atom);
		}
	}

	private List<Holder> allHolders() {
		List<Holder> out = new ArrayList<>();
		for (Map<String, Holder> m : ports.values()) out.addAll(m.values());
		for (Map<String, Holder> m : rewrites.values()) out.addAll(m.values());
		return out;
	}

	// ---- invariants (tests) ------------------------------------------------

	/** Every molecule stands for its plain predicate, and the SplitMap lists
	 *  exactly the atoms each molecule holds. Empty when consistent. */
	public List<String> checkInvariants() {
		List<String> bad = new ArrayList<>();
		for (Holder h : allHolders()) {
			int back = NDD.ref(AtomizedNDD.atomizedToNDD(h.mol));
			if (back != h.pred) bad.add(h.element + "." + h.port + (h.rewrite ? " (rewrite)" : "")
					+ ": molecule != predicate");
			NDD.deref(back);
			HashSet<Integer>[] none = new HashSet[AtomizedNDD.getFieldNum() + 1];
			HashSet<Integer>[] mine = new HashSet[AtomizedNDD.getFieldNum() + 1];
			AtomizedNDD.changeAtoms(AtomizedNDD.getAtomizedFalse(), h.mol, none, mine);
			for (int f = 0; f < mine.length; f++) {
				for (int atom : mine[f]) {
					if (!AtomizedNDD.getAllAtoms(f).contains(atom))
						bad.add(h.element + "." + h.port + ": stale atom " + atom + " on field " + f);
					Set<Holder> s = holders[f].get(atom);
					if (s == null || !s.contains(h))
						bad.add(h.element + "." + h.port + ": atom " + atom + " not mapped to it");
				}
			}
		}
		for (int f = 0; f < holders.length; f++) {
			for (Map.Entry<Integer, Set<Holder>> entry : holders[f].entrySet()) {
				for (Holder h : entry.getValue()) {
					HashSet<Integer>[] none = new HashSet[AtomizedNDD.getFieldNum() + 1];
					HashSet<Integer>[] mine = new HashSet[AtomizedNDD.getFieldNum() + 1];
					AtomizedNDD.changeAtoms(AtomizedNDD.getAtomizedFalse(), h.mol, none, mine);
					if (!mine[f].contains(entry.getKey()))
						bad.add(h.element + "." + h.port + ": mapped to atom " + entry.getKey() + " it lacks");
				}
			}
		}
		return bad;
	}
}
