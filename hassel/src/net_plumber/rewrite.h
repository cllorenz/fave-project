#ifndef REWRITE_H
#define REWRITE_H

#include <bdd.h>
#include "bdd_packet_set.h"

template<class T>
class Rewrite<T> {
    public:
        T *rewrite;

        Rewrite<T>(T *rewrite
#ifdef USE_BDD
            , Mask<T> *mask
#endif
        ) : rewrite(rewrite) {
#ifdef USE_BDD
            bdd tmp = bddtrue;
            for (size_t i = 0; i < mask.fm_len; i++) {
                int idx = mask.fwd_mask[i];

                const bdd ith = bdd_ithvar(idx);
                const bdd nith = bdd_nithvar(idx);

                const bool rw_is_zero = (ith & this->rewrite) == bddfalse;
                const bool rw_is_one = (nith & this->rewrite) == bddfalse;
                const bool rw_is_x = !rw_is_zero && !rw_is_one;

                if (rw_is_x) {
                    ;
                } else if (rw_is_zero) {
                    tmp &= nith;
                } else if (rw_is_one) {
                    tmp &= ith;
                }
            }

            this->rewrite = tmp;
#endif
        }
        ~Rewrite() {
            delete this->rewrite;
        }

        std::string to_str() {
            return this->rewrite->to_str();
        }
};
#endif // REWRITE_H
