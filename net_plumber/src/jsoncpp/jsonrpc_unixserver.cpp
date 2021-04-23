/*
 *  JsonRpc-Cpp - JSON-RPC implementation.
 *  Copyright (C) 2008-2011 Sebastien Vincent <sebastien.vincent@cppextrem.com>
 *  Copyright (C) 2018-2020 Claas Lorenz <cllorenz@uni-potsdam.de>
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
 * \file jsonrpc_UnixServer.cpp
 * \brief JSON-RPC TCP server.
 * \author Sebastien Vincent
 */

#include <stdexcept>

#include "jsonrpc_unixserver.h"

#include "netstring.h"

#include <cstring>
#include <cerrno>


namespace Json
{

  namespace Rpc
  {

    UnixServer::UnixServer(const std::string& address) : Server(address)
    {
    }

    UnixServer::~UnixServer()
    {
      if(m_sock != -1)
      {
        Close();
      }
    }

    ssize_t UnixServer::Send(int fd, const std::string& data)
    {
      std::string rep = data;

      /* encoding if any */
      if(GetEncapsulatedFormat() == Json::Rpc::NETSTRING)
      {
        rep = netstring::encode(rep);
      }

      return ::send(fd, rep.c_str(), rep.length(), 0);
    }

    bool UnixServer::Recv(int fd)
    {
      Json::Value response;
      ssize_t nb = -1;
      /* XXX: changed buffer size to 32768 bytes */
      char buf[32768];

      std::string msg = std::string();

      while (1) {
        nb = recv(fd, buf, sizeof(buf), MSG_PEEK);
        if (nb <= 0) {
          m_purge.push_back(fd);
          return false;
        }

        std::string chunk = std::string(buf, nb);
        size_t pos = chunk.find_first_of('\n');

        if (!pos) { /* message not finished, yet -> receive more chunks */
          msg.append(chunk);
          recv(fd, buf, nb, 0);

        } else { /* message finished -> read rest of message and forward receive buffer */
          msg.append(chunk, 0, pos+1);
          recv(fd, buf, pos+1, 0);
          break;
        }
      }

      /* give the message to JsonHandler */
      if(GetEncapsulatedFormat() == Json::Rpc::NETSTRING)
      {
        try
        {
          msg = netstring::decode(msg);
        }
        catch(const netstring::NetstringException& e)
        {
          /* error parsing Netstring */
          std::cerr << e.what() << std::endl;
          return false;
        }
      }

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

        int bytesToSend = rep.length();
        const char* ptrBuffer = rep.c_str();
        do
        {
          int retVal = send(fd, ptrBuffer, bytesToSend, 0);
          if(retVal == -1)
          {
            /* error */
            std::cerr << "Error while sending data: "
                      << strerror(errno) << std::endl;
            return false;
          }
          bytesToSend -= retVal;
          ptrBuffer += retVal;
        }while(bytesToSend > 0);
      }

      return true;
    }


    void UnixServer::WaitMessage(uint32_t ms)
    {
      fd_set fdsr;
      struct timeval tv;
      int max_sock = m_sock;

      tv.tv_sec = ms / 1000;
      tv.tv_usec = (ms % 1000 ) / 1000;

      FD_ZERO(&fdsr);

#ifdef _WIN32
      /* on Windows, a socket is not an int but a SOCKET (unsigned int) */
      FD_SET((SOCKET)m_sock, &fdsr);
#else
      FD_SET(m_sock, &fdsr);
#endif

      for(std::list<int>::iterator it = m_clients.begin() ; it != m_clients.end() ; it++)
      {
#ifdef _WIN32
        FD_SET((SOCKET)(*it), &fdsr);
#else
        FD_SET((*it), &fdsr);
#endif

        if((*it) > max_sock)
        {
          max_sock = (*it);
        }
      }

      max_sock++;

      if(select(max_sock, &fdsr, NULL, NULL, ms ? &tv : NULL) > 0)
      {
        if(FD_ISSET(m_sock, &fdsr))
        {
          Accept();
        }

        for(std::list<int>::iterator it = m_clients.begin() ; it != m_clients.end() ; it++)
        {
          if(FD_ISSET((*it), &fdsr))
          {
            Recv((*it));
          }
        }

        /* remove disconnect socket descriptor */
        for(std::list<int>::iterator it = m_purge.begin() ; it != m_purge.end() ; it++)
        {
          m_clients.remove((*it));
        }

        /* purge disconnected list */
        m_purge.erase(m_purge.begin(), m_purge.end());
      }
      else
      {
        /* error */
      }
    }

    bool UnixServer::Listen() const
    {
      if(m_sock == -1)
      {
        return false;
      }

      if(listen(m_sock, 5) == -1)
      {
        return false;
      }

      return true;
    }

    bool UnixServer::Accept()
    {
      int client = -1;
      socklen_t addrlen = sizeof(struct sockaddr_storage);

      if(m_sock == -1)
      {
        return false;
      }

      client = accept(m_sock, 0, &addrlen);

      if(client == -1)
      {
        return false;
      }

      m_clients.push_back(client);
      return true;
    }

    void UnixServer::Close()
    {
      /* close all client sockets */
      for(std::list<int>::iterator it = m_clients.begin() ; it != m_clients.end() ; it++)
      {
        ::close((*it));
      }
      m_clients.erase(m_clients.begin(), m_clients.end());

      /* listen socket should be closed in Server destructor */
    }

    const std::list<int> UnixServer::GetClients() const
    {
      return m_clients;
    }

  } /* namespace Rpc */

} /* namespace Json */

