CREATE DATABASE IF NOT EXISTS OSCore CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE OSCore;

CREATE TABLE IF NOT EXISTS simulation_sessions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  session_uuid VARCHAR(64) NOT NULL UNIQUE,
  started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  notes VARCHAR(255) NULL
);
CREATE TABLE IF NOT EXISTS processes (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  session_uuid VARCHAR(64) NOT NULL,
  pid INT NOT NULL,
  process_name VARCHAR(120) NOT NULL,
  arrival_time INT NOT NULL DEFAULT 0,
  burst_time INT NOT NULL DEFAULT 1,
  remaining_time INT NOT NULL DEFAULT 1,
  state VARCHAR(20) NOT NULL DEFAULT 'READY',
  waiting_for VARCHAR(80) NULL,
  progress INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_session_pid (session_uuid,pid),
  INDEX idx_process_state (session_uuid,state)
);
CREATE TABLE IF NOT EXISTS resources (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  resource_name VARCHAR(80) NOT NULL UNIQUE,
  capacity INT NOT NULL,
  available_instances INT NOT NULL
);
CREATE TABLE IF NOT EXISTS resource_allocations (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  session_uuid VARCHAR(64) NOT NULL,
  pid INT NOT NULL,
  resource_name VARCHAR(80) NOT NULL,
  allocation_state ENUM('HELD','WAITING','RELEASED') NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_allocation_session (session_uuid),
  INDEX idx_allocation_pid (session_uuid,pid)
);
CREATE TABLE IF NOT EXISTS process_events (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(64) NULL,
  pid INT NULL,
  event_type VARCHAR(80) NOT NULL,
  description TEXT NOT NULL,
  simulation_time INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_event_session (session_id,id),
  INDEX idx_event_pid (session_id,pid),
  INDEX idx_event_type (event_type)
);
CREATE TABLE IF NOT EXISTS deadlock_events (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  session_uuid VARCHAR(64) NULL,
  detected BOOLEAN NOT NULL,
  involved_pids VARCHAR(255) NULL,
  recovery_action VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO resources (resource_name,capacity,available_instances) VALUES ('printer',2,2),('file_lock',1,1)
ON DUPLICATE KEY UPDATE capacity=VALUES(capacity);
