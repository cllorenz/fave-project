/*
 *  JsonRpc-Cpp - JSON-RPC implementation.
 *  Copyright (C) 2008-2011 Sebastien Vincent <sebastien.vincent@cppextrem.com>
 *
 *  This program is free software: you can redistribute it and/or modify
 *  it under the terms of the GNU Lesser General Public License as published by
 *  the Free Software Foundation, either version 3 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU Lesser General Public License for more details.
 *
 *  You should have received a copy of the GNU Lesser General Public License
 *  along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

/**
 * \file jsonrpc_udpserver.cpp
 * \brief JSON-RPC UDP server.
 * \author Sebastien Vincent
 */

#include <stdexcept>

#include "jsonrpc_udpserver.h"

#include "netstring.h"

namespace Json
{

  namespace Rpc
  {

    UdpServer::UdpServer(const std::string& address, uint16_t port) : Server(address, port)
    {
      m_protocol = networking::UDP;
    }

    UdpServer::~UdpServer()
    {
    }

    ssize_t UdpServer::Send(const std::string& data, const struct sockaddr* addr,
        socklen_t addrlen)
    {
      std::string rep = data;

      /* encoding if any */
      if(GetEncapsulatedFormat() == Json::Rpc::NETSTRING)
      {
        rep = netstring::encode(rep);
      }

      return ::sendto(m_sock, rep.c_str(), rep.length(), 0, (struct sockaddr*)addr, addrlen);
    }

    bool UdpServer::Recv(int fd)
    {
      Json::Value response;
      ssize_t nb = -1;
      /* XXX: changed buffer size to 32768 bytes */
      char buf[32768];
      struct sockaddr_storage addr;
      socklen_t addrlen = sizeof(struct sockaddr_storage);


      std::string msg = std::string();

      while (1) {
        nb = ::recvfrom(fd, buf, sizeof(buf), MSG_PEEK, (struct sockaddr*)&addr, &addrlen);
        if (nb <= 0) {
          return false;
        }

        std::string chunk = std::string(buf, nb);
        size_t pos = chunk.find_first_of('\n');

        if (pos == std::string::npos) { /* message not finished, yet -> receive more chunks */
          msg.append(chunk);
          ::recvfrom(fd, buf, nb, 0, (struct sockaddr*)&addr, &addrlen);

        } else { /* message finished -> read rest of message and forward receive buffer */
          msg.append(chunk, 0, pos+1);
          ::recvfrom(fd, buf, pos+1, 0, (struct sockaddr*)&addr, &addrlen);
          break;
        }
      }


      if(GetEncapsulatedFormat() == Json::Rpc::NETSTRING)
      {
        try
        {
          msg = netstring::decode(msg);
        }
        catch(const netstring::NetstringException& e)
        {
          /* error parsing NetString */
          std::cerr << e.what() << std::endl;
          return false;
        }
      }

      /* give the message to JsonHandler */
      m_jsonHandler.Process(msg, response);

      /* in case of notification message received, the response could be Json::Value::null */
      if(response != Json::Value::null)
      {
        std::string rep = m_jsonHandler.GetString(response);

        /* encoding */
        if(GetEncapsulatedFormat() == Json::Rpc::NETSTRING)
        {
          rep = netstring::encode(rep);
        }

        if(::sendto(fd, rep.c_str(), rep.length(), 0, (struct sockaddr*)&addr, addrlen) == -1)
        {
          /* error */
          std::cerr << "Error while sending"  << std::endl;
          return false;
        }
      }

      return true;
    }

    void UdpServer::WaitMessage(uint32_t ms)
    {
      fd_set fdsr;
      struct timeval tv;
      int max_sock = m_sock;

      max_sock++;

      FD_ZERO(&fdsr);

#ifdef _WIN32
      /* on Windows, a socket is not an int but a SOCKET (unsigned int) */
      FD_SET((SOCKET)m_sock, &fdsr);
#else
      FD_SET(m_sock, &fdsr);
#endif

      tv.tv_sec = ms / 1000;
      tv.tv_usec = (ms % 1000) * 1000;

      if(select(max_sock, &fdsr, NULL, NULL, ms ? &tv : NULL) > 0)
      {
        if(FD_ISSET(m_sock, &fdsr))
        {
          Recv(m_sock);
        }
      }
      else
      {
        /* problem */
      }
    }

  } /* namespace Rpc */

} /* namespace Json */

