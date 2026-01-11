## 1. Implementation
- [ ] 1.1 Add Redis job store, queue, and lock helpers
- [ ] 1.2 Update JobManager to support api/worker/all roles and Redis-backed store/queue
- [ ] 1.3 Add worker entrypoint for Redis queue consumption and segment processing
- [ ] 1.4 Update merged audio endpoint to use Redis lock when configured
- [ ] 1.5 Implement Redis-backed active job backpressure accounting
- [ ] 1.6 Update docker-compose for redis/api/worker/web and shared cache volume
- [ ] 1.7 Add tests for Redis store enqueue and lock wrapper (skip when Redis unavailable)
