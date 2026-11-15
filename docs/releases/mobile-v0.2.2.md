# AutoRIP Mobile 0.2.2 (prévia)

O app conecta o telefone ao painel do AutoRIP; o computador continua executando o RIP.

- JavaScript solicitado na abertura reduzido de 32.656 para 2.432 bytes (92,55%); o leitor QR e o runtime Capacitor são carregados ao abrir a câmera. Isso não equivale a uma redução de 92% no APK nem a um tempo de abertura medido em Android físico.
- Conexão manual continua funcionando quando o armazenamento do histórico está indisponível. O histórico exibe até cinco servidores, inclusive ao ler listas antigas maiores.
- Com **AutoRIP 0.8.29**, use **Conectar celular** no computador para ativar o IPv4 e gerar o QR. Vários telefones podem fazer login sem encerrar as sessões anteriores e sem teto numérico de aparelhos no AutoRIP.
- Depois de conectar e entrar, use **Enviar arquivos**, escolha **Arquivos do aparelho** ou **Fotos da galeria**, confira a largura e confirme o envio. Há seleção múltipla, progresso e confirmação da fila. PNG, JPEG e TIFF são aceitos; HEIC precisa ser exportado para PNG/JPEG.
- O painel do servidor também oferece contas de IA por provedor e consultas de acompanhamento com menos tráfego quando não há mudanças.

Artefatos:

- `AutoRIP-Mobile-debug.apk`: Android padrão, assinado com chave debug de teste.
- `AutoRIP-Mobile-optimized.apk`: variante R8 de teste, instalada como app separado.
- `AutoRIP-Mobile-release-unsigned.apk`: compilação release sem assinatura de produção.
- `AutoRIP-iOS-unsigned.app.zip`: aplicativo iOS compilado sem assinatura; exige Mac/Xcode e assinatura Apple para instalar em aparelho. Não é um IPA nem publicação na App Store/TestFlight.
- `COMO_USAR.txt` e `SHA256SUMS.txt`.

Os APKs de prévia podem exigir desinstalar uma prévia anterior por diferença de assinatura; isso remove o histórico local do app, não os arquivos do computador. Os testes desta rodada usam navegador e seletores simulados, com HTTP real; não substituem validação num telefone físico.

[Guia de instalação e conexão](https://github.com/Giblxv/Autorip/blob/main/docs/GUIA-APPS-MOVEIS.md).
