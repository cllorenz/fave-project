/*
   Copyright 2012 Google Inc.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

   Authors: peyman.kazemian@gmail.com (Peyman Kazemian)
            kiekhebe@uni-potsdam.de (Sebastian Kiekheben)
            cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#ifndef SRC_NET_PLUMBER_CONDITIONS_H_
#define SRC_NET_PLUMBER_CONDITIONS_H_

#include "node.h"
#include <string>
#include "net_plumber_utils.h"
#include "../jsoncpp/json/json.h"
#include "log4cxx/logger.h"

/*
 * Language for describing policy using Conditions:
 *
 * Condition:     True OR
 *                False OR
 *                PathCondition OR
 *                HeaderCondition OR
 *                (Condition | Condition) OR
 *                (Condition & Condition) OR
 *                !Condition;
 * PathCondition: list(PathSpecifier);
 * PathSpecifier: PortSpecifier OR
 *                TableSpecifier OR
 *                NextPortsSpecifier OR
 *                NextTablesSpecifier OR
 *                LastPortsSpecifier OR
 *                LastTablesSpecifier OR
 *                SkipNextSpecifier OR
 *                EndPathSpecifier;
 *
 * Note: LastPortsSpecifier and LastTablesSpecifier are only an optimization.
 * They could be created using other specifiers, but given the wide use of these
 * specifiers, they are added here.
 */

enum PATHLET_TYPE {
    PATHLET_BASE = 0,
    PATHLET_SKIP,
    PATHLET_END,
    PATHLET_SKIP_NEXT,
    PATHLET_NEXT_PORT,
    PATHLET_NEXT_TABLE,
    PATHLET_PORTS,
    PATHLET_TABLES,
    PATHLET_LAST_PORTS,
    PATHLET_LAST_TABLES
};

template<class T1, class T2>
class Condition {
  protected:
    static log4cxx::LoggerPtr logger;

 public:
  Condition() {};
  virtual void enlarge(uint32_t) {};
  virtual ~Condition() {};
  virtual bool check(Flow<T1, T2> *f) = 0;
  virtual std::string to_string() = 0;

  virtual void to_json(Json::Value&) = 0;
};

template<class T1, class T2>
class TrueCondition : public Condition<T1, T2> {
  /*
   * always true
   */
 public:
  TrueCondition() {};
  virtual ~TrueCondition() {};
  bool check(Flow<T1, T2> * /*f*/) { return true; }
  std::string to_string() { return "Always True"; }
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class FalseCondition : public Condition<T1, T2> {
  /*
   * always false
   */
 public:
  FalseCondition() {};
  virtual ~FalseCondition() {};
  bool check(Flow<T1, T2> * /*f*/) { return false; }
  std::string to_string() { return "Always False"; }
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class AndCondition : public Condition<T1, T2> {
  /*
   * (c1 & c2)
   */
 private:
  Condition<T1, T2> *c1;
  Condition<T1, T2> *c2;
 public:
  AndCondition(Condition<T1, T2> *c1, Condition<T1, T2> *c2) : c1(c1), c2(c2) {}
  void enlarge(uint32_t length) {c1->enlarge(length);c2->enlarge(length);};
  virtual ~AndCondition() {delete c1; delete c2;}
  bool check(Flow<T1, T2> *f) {return c1->check(f) && c2->check(f);}
  std::string to_string() {
    return "(" + c1->to_string() + ") & (" + c2->to_string() + ")";
  }
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class OrCondition : public Condition<T1, T2> {
  /*
   * (c1 | c2)
   */
 private:
  Condition<T1, T2> *c1;
  Condition<T1, T2> *c2;
 public:
  OrCondition(Condition<T1, T2> *c1, Condition<T1, T2> *c2) : c1(c1), c2(c2) {}
  void enlarge(uint32_t length) {c1->enlarge(length);c2->enlarge(length);};
  virtual ~OrCondition() {delete c1; delete c2;}
  bool check(Flow<T1, T2> *f) {return c1->check(f) || c2->check(f);}
  std::string to_string() {
    return "(" + c1->to_string() + ") | (" + c2->to_string() + ")";
  }
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class NotCondition : public Condition<T1, T2> {
  /*
   * (!c)
   */
 private:
  Condition<T1, T2> *c;
 public:
  NotCondition(Condition<T1, T2> *c) : c(c) {}
  void enlarge(uint32_t length) {c->enlarge(length);};
  virtual ~NotCondition() {delete c;}
  bool check(Flow<T1, T2> *f) {return !c->check(f);}
  std::string to_string() {return "!(" + c->to_string() + ")";}
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class HeaderCondition : public Condition<T1, T2> {
  /*
   * header intersect h != empty
   */
 protected:
  T1 *h;
 public:
  HeaderCondition(T1 *match_header) : h(match_header) {}
  ~HeaderCondition() { delete h; }
  void enlarge(uint32_t length);
  bool check(Flow<T1, T2> *f);
  std::string to_string();
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class PathSpecifier;
template<class T1, class T2>
class PathCondition : public Condition<T1, T2> {
  /*
   * the regexp obtained by concat'ing pathlets.
   */
 protected:
  std::list<PathSpecifier<T1, T2>*> pathlets;
 public:
  PathCondition() {}
  virtual ~PathCondition();
  void add_pathlet(PathSpecifier<T1, T2> *pathlet);
  bool check(Flow<T1, T2> *f);
  std::string to_string();
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class PathSpecifier {
 protected:
  PATHLET_TYPE type;
 public:
  virtual bool check_and_move(Flow<T1, T2>* &f) = 0;
  virtual std::string to_string() = 0;
  PathSpecifier() : type(PATHLET_BASE) {}
  PathSpecifier(PATHLET_TYPE t) : type(t) {}
  virtual ~PathSpecifier() {}
  PATHLET_TYPE get_type() { return type; }

  virtual void to_json(Json::Value&) = 0;
};

template<class T1, class T2>
class PortSpecifier : public PathSpecifier<T1, T2> {
  /*
   * .*(p = @port)
   */
 private:
  uint32_t port;
 public:
  PortSpecifier<T1, T2>(uint32_t p) : PathSpecifier<T1, T2>(PATHLET_NEXT_PORT), port(p) {}
  ~PortSpecifier() {}
  bool check_and_move(Flow<T1, T2>* &f);
  std::string to_string();
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class TableSpecifier : public PathSpecifier<T1, T2> {
  /*
   * .*(t = @table)
   */
 private:
  uint32_t table;
 public:
  TableSpecifier(uint32_t t) : PathSpecifier<T1, T2>(PATHLET_NEXT_TABLE),table(t) {}
  ~TableSpecifier() {}
  bool check_and_move(Flow<T1, T2>* &f);
  std::string to_string();
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class NextPortsSpecifier : public PathSpecifier<T1, T2> {
  /*
   * (p in @ports)
   */
 private:
  List_t ports;
 public:
  NextPortsSpecifier<T1, T2>(List_t ports) : PathSpecifier<T1, T2>(PATHLET_PORTS),ports(ports) {}
  ~NextPortsSpecifier() {free(ports.list);}
  bool check_and_move(Flow<T1, T2>* &f);
  std::string to_string();
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class NextTablesSpecifier : public PathSpecifier<T1, T2> {
  /*
   * (t in @tables)
   */
 private:
  List_t tables;
 public:
  NextTablesSpecifier(List_t tables) : PathSpecifier<T1, T2>(PATHLET_TABLES),tables(tables) {}
  ~NextTablesSpecifier() {free(tables.list);}
  bool check_and_move(Flow<T1, T2>* &f);
  std::string to_string();
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class LastPortsSpecifier : public PathSpecifier<T1, T2> {
  /*
   * checks whether the last port is in @ports
   * .*(p in @ports)$
   */
 private:
  List_t ports;
 public:
  LastPortsSpecifier(List_t ports) : PathSpecifier<T1, T2>(PATHLET_LAST_PORTS),ports(ports) {}
  ~LastPortsSpecifier() {free(ports.list);}
  bool check_and_move(Flow<T1, T2>* &f);
  std::string to_string();
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class LastTablesSpecifier : public PathSpecifier<T1, T2> {
  /*
   * checks whether the last table is in @ports
   * .*(t in @tables)$
   */
 private:
  List_t tables;
 public:
  LastTablesSpecifier(List_t tables) : PathSpecifier<T1, T2>(PATHLET_LAST_TABLES),tables(tables) {}
  ~LastTablesSpecifier() {free(tables.list);}
  bool check_and_move(Flow<T1, T2>* &f);
  std::string to_string();
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class SkipNextSpecifier : public PathSpecifier<T1, T2> {
  /*
   * "." regexp
   */
 public:
  SkipNextSpecifier() : PathSpecifier<T1, T2>(PATHLET_SKIP) {}
  ~SkipNextSpecifier() {}
  bool check_and_move(Flow<T1, T2>* &f);
  std::string to_string() {return ".";}
  virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class SkipNextArbSpecifier : public PathSpecifier<T1, T2> {
  /*
   * ".*" regexp
   */
  public:
    SkipNextArbSpecifier() : PathSpecifier<T1, T2>(PATHLET_SKIP_NEXT) {}
    ~SkipNextArbSpecifier() {}
    bool check_and_move(Flow<T1, T2>* &f);
    std::string to_string() {return ".*";}
    virtual void to_json(Json::Value&);
};

template<class T1, class T2>
class EndPathSpecifier : public PathSpecifier<T1, T2> {
  /*
   * $ - checks if we are at the end of path.
   */
 public:
  EndPathSpecifier() : PathSpecifier<T1, T2>(PATHLET_END) {}
  ~EndPathSpecifier() {}
  bool check_and_move(Flow<T1, T2>* &f) {return f->p_flow == f->node->get_EOSFI();}
  std::string to_string() { return "$";}
  virtual void to_json(Json::Value&);
};

#endif  // SRC_NET_PLUMBER_CONDITIONS_H_
