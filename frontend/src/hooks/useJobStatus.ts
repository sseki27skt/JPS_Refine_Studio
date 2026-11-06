// -*- coding: utf-8 -*-
/**
 * SSE (Server-Sent Events) を用いたリアルタイムジョブ進捗監視フック
 */
import { useState, useEffect, useRef } from 'react';
import { JobProgress } from '../types/api';

export function useJobStatus(jobId: string | null, onCompleted?: (job: JobProgress) => void) {
  const [job, setJob] = useState<JobProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const onCompletedRef = useRef(onCompleted);
  onCompletedRef.current = onCompleted;

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setIsConnected(false);
      return;
    }

    const eventSource = new EventSource(`/api/jobs/${jobId}/stream`);

    eventSource.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    eventSource.addEventListener('progress', (e) => {
      try {
        const data: JobProgress = JSON.parse(e.data);
        setJob(data);
      } catch (err) {
        console.error('Failed to parse SSE progress data:', err);
      }
    });

    eventSource.addEventListener('done', (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.status === 'COMPLETED' && onCompletedRef.current && job) {
          onCompletedRef.current(job);
        }
      } catch (err) {
        console.error('Failed to parse SSE done data:', err);
      }
      eventSource.close();
      setIsConnected(false);
    });

    eventSource.onerror = (err) => {
      console.warn('SSE connection error or closed:', err);
      setIsConnected(false);
      eventSource.close();
    };

    return () => {
      eventSource.close();
      setIsConnected(false);
    };
  }, [jobId]);

  return { job, error, isConnected };
}

