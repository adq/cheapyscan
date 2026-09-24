// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Andrew de Quincey

import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'
import { live } from './lib/live.svelte'

live.start()

export default mount(App, { target: document.getElementById('app')! })
