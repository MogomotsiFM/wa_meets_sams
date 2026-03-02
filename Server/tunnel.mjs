import process from 'process';

import localtunnel from 'localtunnel';

async function setupTunnel(port, subdomain) {
    const tunnel = await localtunnel({ port: port, subdomain: subdomain });

    // The assigned public URL
    //console.log('Your tunnel URL:', tunnel.url);
    return tunnel.url;
};


process.stdin.on('data', (data) => {
    try {
        const input = JSON.parse(data.toString());
        const port = input.port;
        const subdomain = input.subdomain;

        (async () => {
            const tunnel_url = await setupTunnel(port, subdomain);
            console.log(JSON.stringify({tunnel_url: tunnel_url}));
        })();

    } catch (err) {
        console.error(JSON.stringify({'Error:': err.message}));
    }
});