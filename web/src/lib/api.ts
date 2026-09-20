/**
 * REST client. Plain fetch against /api, proxied to Django by Vite in dev.
 *
 * There is no websocket anywhere in this project. The client owns the clock:
 * it steps the server-held simulation and animates between the frames it gets
 * back. That is what makes the demo safe to run on stage.
 */

export {};
