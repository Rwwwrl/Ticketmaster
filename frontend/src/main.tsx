import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { Amplify } from 'aws-amplify';
import { App } from './App.tsx';

const { userPoolId, userPoolClientId, domain } = window.__APP_CONFIG__.cognito;

Amplify.configure({
    Auth: {
        Cognito: {
            userPoolId,
            userPoolClientId,
            loginWith: {
                oauth: {
                    domain,
                    scopes: ['openid', 'email', 'profile'],
                    redirectSignIn: [`${window.location.origin}/auth/callback`],
                    redirectSignOut: [`${window.location.origin}/`],
                    responseType: 'code',
                },
            },
        },
    },
});

createRoot(document.getElementById('root')!).render(
    <StrictMode>
        <BrowserRouter>
            <App />
        </BrowserRouter>
    </StrictMode>,
);
