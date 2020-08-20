// 2020 Copyright by hagersve@hu-berlin.de
// Algorithm from Y. Chang. "A 2-Level TCAM Architecture for Ranges". In: IEEE
// Transactions on Computers, 2006.

void
Rule_dim_range_to_prefix(const Rule* rule,
                         const size_t dim,
                         Ruleset* ruleset) {

  ASSERT(dim < ruleset->num_fields_);
  ASSERT(dim < rule->num_fields_);
  FieldCheck* check = rule->checks_[dim];

  if (check->type_ == EXACT) {
    Rule* new_rule = Rule_clone(rule);
    new_rule->checks_[dim]->type_ = SUBNET;
    new_rule->checks_[dim]->second_ = ruleset->field_bits_[dim];
    Ruleset_append(ruleset, new_rule);
    return;
  }

  if (check->type_ == SUBNET) {
    Rule* new_rule = Rule_clone(rule);
    Ruleset_append(ruleset, new_rule);
    return;
  }

  if (check->type_ == RANGE) {
    const FieldVal num_bits = ruleset->field_bits_[dim];

    FieldVal start = check->first_;
    FieldVal end   = check->second_;
    while (start <= end) {
      for (FieldVal i = 0; i <= num_bits; ++i) {
        FieldVal pot = 1 << (i + 1);
        if (((start % pot) != 0) || ((start + pot - 1) > end)) {
          FieldVal prefix_start = start;
          start = start + (1 << i);
          Rule* new_rule = Rule_clone(rule);
          new_rule->checks_[dim]->type_ = SUBNET;
          new_rule->checks_[dim]->first_ = prefix_start;
          const FieldVal mask = num_bits - i;
          new_rule->checks_[dim]->second_ = mask;
          Ruleset_append(ruleset, new_rule);
          break;
        }
      }
    }
    return;
  }
  assert(0); // should never reach this point
}
