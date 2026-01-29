// Service Worker for Vocabulary Pro - Offline First with Background Sync

const CACHE_NAME = 'vocab-pro-cache-v4.3';
const API_URL = 'http://localhost:8000/api'; // Your Flask server

// Files to cache immediately
const urlsToCache = [
  '/app-full',
  '/',
  '/manifest.json',
  'https://fonts.googleapis.com/icon?family=Material+Icons+Round'
];

// Install event - cache essential files
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('📦 Caching essential files');
        return cache.addAll(urlsToCache);
      })
      .then(() => self.skipWaiting())
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('🗑️ Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Helper: Queue offline requests for later sync
function queueRequest(request) {
  return caches.open('offline-queue')
    .then(cache => {
      const queueItem = {
        url: request.url,
        method: request.method,
        headers: {},
        body: null,
        timestamp: Date.now()
      };

      // Clone and store request body for POST requests
      if (request.method === 'POST') {
        return request.clone().text().then(body => {
          queueItem.body = body;
          queueItem.headers['Content-Type'] = 'application/json';
          return cache.put(
            `queue-${Date.now()}`,
            new Response(JSON.stringify(queueItem))
          );
        });
      } else {
        return cache.put(
          `queue-${Date.now()}`,
          new Response(JSON.stringify(queueItem))
        );
      }
    })
    .then(() => {
      console.log('📝 Queued offline request:', request.url);
      return new Response(JSON.stringify({
        status: 'queued',
        message: 'Request queued for sync when online',
        timestamp: new Date().toISOString()
      }), {
        headers: { 'Content-Type': 'application/json' }
      });
    });
}

// Helper: Process offline queue when back online
function processOfflineQueue() {
  return caches.open('offline-queue')
    .then(cache => cache.keys())
    .then(keys => {
      const promises = keys.map(key => {
        return caches.match(key)
          .then(response => response.json())
          .then(queueItem => {
            console.log('🔄 Processing queued request:', queueItem.url);
            
            const fetchOptions = {
              method: queueItem.method,
              headers: queueItem.headers
            };

            if (queueItem.body) {
              fetchOptions.body = queueItem.body;
            }

            // Retry the request
            return fetch(queueItem.url, fetchOptions)
              .then(response => {
                if (response.ok) {
                  // Remove from queue on success
                  return caches.delete(key)
                    .then(() => {
                      console.log('✅ Successfully synced queued request');
                      return response;
                    });
                }
                throw new Error('Sync failed');
              })
              .catch(error => {
                console.warn('⚠️ Failed to sync queued request:', error);
                return Promise.resolve(); // Keep in queue for next attempt
              });
          });
      });

      return Promise.all(promises);
    });
}

// Fetch event - Offline First strategy
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);

  // API requests: Network First, Fallback to Queue
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request)
        .then(response => {
          // Clone response to cache
          const responseClone = response.clone();
          caches.open(CACHE_NAME)
            .then(cache => cache.put(request, responseClone));
          return response;
        })
        .catch(() => {
          // Offline: Try cache first, then queue
          return caches.match(request)
            .then(cachedResponse => {
              if (cachedResponse) {
                return cachedResponse;
              }
              // Queue for later sync
              if (request.method === 'POST' || request.method === 'DELETE') {
                return queueRequest(request);
              }
              // For GET requests, return offline response
              return new Response(JSON.stringify({
                status: 'offline',
                message: 'You are offline. Data will sync when connection is restored.',
                data: []
              }), {
                headers: { 'Content-Type': 'application/json' }
              });
            });
        })
    );
  } else {
    // Static assets: Cache First strategy
    event.respondWith(
      caches.match(request)
        .then(response => {
          if (response) {
            return response;
          }
          
          // Not in cache, fetch from network
          return fetch(request)
            .then(response => {
              // Don't cache if not a valid response
              if (!response || response.status !== 200) {
                return response;
              }

              // Clone response to cache
              const responseToCache = response.clone();
              caches.open(CACHE_NAME)
                .then(cache => {
                  cache.put(request, responseToCache);
                });

              return response;
            })
            .catch(() => {
              // Return offline fallback for HTML pages
              if (request.headers.get('Accept').includes('text/html')) {
                return caches.match('/app-full')
                  .then(cachedResponse => cachedResponse || 
                    new Response('<h1>You are offline</h1><p>Please check your connection.</p>', {
                      headers: { 'Content-Type': 'text/html' }
                    })
                  );
              }
              
              // Return offline fallback for other assets
              return new Response('Offline', {
                headers: { 'Content-Type': 'text/plain' }
              });
            });
        })
    );
  }
});

// Listen for messages from the main thread
self.addEventListener('message', event => {
  if (event.data.type === 'SYNC_QUEUE') {
    processOfflineQueue()
      .then(() => {
        event.ports[0].postMessage({ status: 'synced' });
      })
      .catch(error => {
        event.ports[0].postMessage({ status: 'error', error: error.message });
      });
  }
});

// Listen for online/offline events
self.addEventListener('online', () => {
  console.log('🌐 Online - processing queued requests...');
  processOfflineQueue()
    .then(() => {
      // Notify all clients that sync is complete
      self.clients.matchAll().then(clients => {
        clients.forEach(client => {
          client.postMessage({
            type: 'SYNC_COMPLETE',
            message: 'Offline changes synchronized'
          });
        });
      });
    });
});

self.addEventListener('offline', () => {
  console.log('📴 Offline - working in offline mode');
  self.clients.matchAll().then(clients => {
    clients.forEach(client => {
      client.postMessage({
        type: 'OFFLINE_MODE',
        message: 'Working offline'
      });
    });
  });
});

// Background Sync (if supported)
if ('periodicSync' in self.registration && 'permissions' in navigator) {
  navigator.permissions.query({ name: 'periodic-background-sync' })
    .then(permissionStatus => {
      if (permissionStatus.state === 'granted') {
        self.registration.periodicSync.register('vocab-sync', {
          minInterval: 5 * 60 * 1000, // 5 minutes
        });
      }
    });
}