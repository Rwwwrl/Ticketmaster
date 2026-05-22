/// <reference types="vite/client" />

interface AppConfig {
    cognito: {
        userPoolId: string;
        userPoolClientId: string;
        domain: string;
    };
}

declare global {
    interface Window {
        __APP_CONFIG__: AppConfig;
    }
}

export {};
