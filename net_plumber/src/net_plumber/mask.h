/*
   Copyright 2020 Claas Lorenz

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   Author: cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#ifndef MASK_H
#define MASK_H

#include <bdd.h>
#include "bdd_packet_set.h"

template<class T>
class Mask<T> {
    public:
        T *mask;
#ifdef USE_BDD
        int *fwd_mask = nullptr;
        size_t fm_len = 0;
        int *inv_mask = nullptr;
        size_t im_len = 0;
        int creation_varnum;
#endif

        Mask<T>(T *mask) : mask(mask) {
#ifdef USE_BDD
            this->creation_varnum = bdd_varnum();

            int f_mask[this->creation_varnum];
            int i_mask[this->creation_varnum];

            for (int i = 0; i < this->creation_varnum; i++) {
                const bdd nith = bdd_nithvar(i);
                const bool mask_is_one = (nith & this->mask) == bddfalse;

                if (mask_is_one) {
                    f_mask[this->fm_len++] = i;
                } else {
                    i_mask[this->im_len++] = i;
                }
            }

            if (fm_len) {
                fwd_mask = (int)calloc(fm_len, sizeof(int));
                memcpy(fwd_mask, f_mask, fm_len * sizeof(int));
            }
            if (im_len) {
                inv_mask = (int)calloc(im_len, sizeof(int));
                memcpy(inv_mask, i_mask, im_len * sizeof(int));
            }
#endif
        }
        ~Mask<T>() {
            delete this->mask;
#ifdef USE_BDD
            if (this->fwd_mask) free (this->fwd_mask);
            if (this->inv_mask) free (this->inv_mask);
#endif
        }

        std::string to_str() {
            return this->mask->to_str();
        }
};
#endif // MASK_H
