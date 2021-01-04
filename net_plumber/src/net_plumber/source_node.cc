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
            cllorenz@uni-potsdam.de (Claas Lorenz)
*/

#include "source_node.h"
#include "net_plumber_utils.h"
#include <sstream>
#include <string>
#include "array_packet_set.h"
#include "hs_packet_set.h"
#ifdef USE_BDD
#include "bdd_packet_set.h"
#endif

using namespace std;
using namespace log4cxx;
using namespace net_plumber;

template<class T1, class T2>
LoggerPtr SourceNode<T1, T2>::source_logger(Logger::getLogger("SourceNode"));

template<class T1, class T2>
SourceNode<T1, T2>::SourceNode(void *n, int length, uint64_t node_id, T1 *hs_object,
                       List_t ports)
  : Node<T1, T2>(n,length,node_id) {
  this->node_type = SOURCE;
  this->match = nullptr;
  this->inv_match = new T2(length, BIT_X);
  this->output_ports = ports;
  this->input_ports = make_sorted_list(0);
  // create the flow;
  Flow<T1, T2> *f = (Flow<T1, T2> *)malloc(sizeof *f);
  f->node = this;
  f->hs_object = hs_object;
  f->processed_hs = new T1(*hs_object);
  f->in_port = 0;
  f->p_flow = this->source_flow.end();
  f->n_flows = new list< typename list< Flow<T1, T2> *>::iterator >();
  this->source_flow.push_back(f);
}

template<class T1, class T2>
SourceNode<T1, T2>::~SourceNode() {
  // do nothing
}

template<class T1, class T2>
string SourceNode<T1, T2>::source_to_str() {
  stringstream result;
  result << "Source: " << (*this->source_flow.begin())->hs_object->to_str();
  result << " Ports: " << list_to_string(this->output_ports);
  return result.str();
}

template<class T1, class T2>
string SourceNode<T1, T2>::to_string() {
  stringstream result;
  result << string(40, '=') << "\n";
  result << " Source: 0x" << std::hex << this->node_id << "\n";
  result << string(40, '=') << "\n";
  result << source_to_str() << "\n";
  result << this->pipeline_to_string();
  result << this->src_flow_to_string();
  return result.str();
}

template<class T1, class T2>
void SourceNode<T1, T2>::process_src_flow_at_location(
    typename list< Flow<T1, T2> *>::iterator /*loc*/, T2* /*change*/) {
  // do nothing
  stringstream error_msg;
  error_msg << "Called process_src_flow_at_location on SourceNode 0x";
  error_msg << std::hex << this->node_id << ". Unexpected behavior.";
  LOG4CXX_FATAL(source_logger,error_msg.str());
}

template<class T1, class T2>
void SourceNode<T1, T2>::process_src_flow(Flow<T1, T2>* /*f*/) {
  this->propagate_src_flow_on_pipes(this->source_flow.begin());
}

template<class T1, class T2>
void SourceNode<T1, T2>::enlarge(uint32_t length) {
    if (this->logger->isTraceEnabled()) {
      stringstream enl;
      enl << "SourceNode::enlarge(): id 0x" << std::hex << this->node_id;
      enl << " enlarge from " << std::dec << this->length << " to " << length;
      LOG4CXX_TRACE(this->logger, enl.str());
    }
	if (length <= this->length) {
		return;
	}
	Node<T1, T2>::enlarge(length);
    LOG4CXX_TRACE(this->logger, "SourceNode::enlarge(): set length\n");
	this->length = length;
}

template class SourceNode <HeaderspacePacketSet, ArrayPacketSet>;
#ifdef USE_BDD
template class SourceNode <BDDPacketSet, BDDPacketSet>;
#endif
