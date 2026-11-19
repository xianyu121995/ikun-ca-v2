'use client';
import {createContext, useContext} from 'react';
import type {TrackingVoiceController} from '@ikun/ui';

export const VoiceContext = createContext<TrackingVoiceController | null>(null);
export const useSiteVoice = () => useContext(VoiceContext);
