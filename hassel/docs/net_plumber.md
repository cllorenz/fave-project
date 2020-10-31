# NetPlumber Data Structures



## Wildcard Vectors: `array_t`

TODO: document

## Wildcard Expressions: `struct hs_vec`

    struct hs_vec {
      array_t **elems;
      size_t used, alloc;
    };

A wildcard expression consists of a list `elems` of wildcard vectors. The field `alloc` stores the allocated slots (i.e. the capacity) whereas `used` indicates how many slots are filled.

## Headerspaces: `struct hs`

    struct hs {
      size_t len;
      struct hs_vec list;
      struct hs_vec diff;
    };

Headerspaces are represented by two wildcard expressions - a positive list `list` and a negative list `diff`: $A - A_d$. Also, the length `len` of stored wildcard vectors is given. Note that all vectors must have the same length.

# NetPlumber Operations


## Intersection: `hs_isect(hs *a, hs *b)`

$(A - A_d) \cap (B - B_d) = (A \cap B) - (A_d \cup B_d)$

## Union: `hs_union(hs *a, hs *b)`

$(A - A_d) \cup (B - B_d) = (A \cup B) - (A_d \cup B_d)$

## Complement: `hs_cmpl(hs *h)`

$\overline{(A - A_d)} = \Omega - (A - A_d) = \Omega - (A \cap \overline{A_d})$

## Difference: `hs_minus(hs *a, hs *b)`

$(A - A_d) - (B - B_d) = (A - A_d) \cap \overline{(B - B_d)}$

## Emptiness Check: `hs_is_empty(hs *h)`

Checks whether a given headerspace object is empty: $(A - A_d) \overset{?}{=} \emptyset$.

## Check for the All Set: `hs_is_all(hs *h)`

Checks whether a given headerspace object represents the All set: $(A - A_d) \overset{?}{=} \Omega$.

## Subset or Equal Check: `hs_is_sub_eq(hs *a, hs *b)`

Checks whether a headerspace object is a subset of or equal to another headerspace object:

$(A - A_d) \subseteq (B - B_d) <=> (A - A_d) \cap (B - B_d) \not= \emptyset \land (A - A_d) - (B - B_d) = \emptyset$.

## Equality Check: `hs_is_eq(hs *a, hs *b)`

Checks whether two headerspace objects are equal:

$(A - A_d) = (B - B_d) <=> (A - A_d) \subseteq (B - B_d) \land (B - B_d) \subseteq (A - A_d)$

## Subset Check: `hs_is_sub(hs *a, hs *b)`

Checks whether a headerspace is a true subset of another headerspace:

$(A - A_d) = (B - B_d) <=> (A - A_d) \subseteq (B - B_d) \land \lnot((B - B_d) \subseteq (A - A_d))$
