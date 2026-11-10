(() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __esm = (fn, res) => function __init() {
    return fn && (res = (0, fn[__getOwnPropNames(fn)[0]])(fn = 0)), res;
  };
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };

  // node_modules/@capacitor/core/dist/index.js
  var createCapacitorPlatforms, initPlatforms, CapacitorPlatforms, addPlatform, setPlatform, ExceptionCode, CapacitorException, getPlatformId, createCapacitor, initCapacitorGlobal, Capacitor, registerPlugin, Plugins, WebPlugin, encode, decode, CapacitorCookiesPluginWeb, CapacitorCookies, readBlobAsBase64, normalizeHttpHeaders, buildUrlParams, buildRequestInit, CapacitorHttpPluginWeb, CapacitorHttp;
  var init_dist = __esm({
    "node_modules/@capacitor/core/dist/index.js"() {
      createCapacitorPlatforms = (win) => {
        const defaultPlatformMap = /* @__PURE__ */ new Map();
        defaultPlatformMap.set("web", { name: "web" });
        const capPlatforms = win.CapacitorPlatforms || {
          currentPlatform: { name: "web" },
          platforms: defaultPlatformMap
        };
        const addPlatform2 = (name, platform) => {
          capPlatforms.platforms.set(name, platform);
        };
        const setPlatform2 = (name) => {
          if (capPlatforms.platforms.has(name)) {
            capPlatforms.currentPlatform = capPlatforms.platforms.get(name);
          }
        };
        capPlatforms.addPlatform = addPlatform2;
        capPlatforms.setPlatform = setPlatform2;
        return capPlatforms;
      };
      initPlatforms = (win) => win.CapacitorPlatforms = createCapacitorPlatforms(win);
      CapacitorPlatforms = /* @__PURE__ */ initPlatforms(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : typeof global !== "undefined" ? global : {});
      addPlatform = CapacitorPlatforms.addPlatform;
      setPlatform = CapacitorPlatforms.setPlatform;
      (function(ExceptionCode2) {
        ExceptionCode2["Unimplemented"] = "UNIMPLEMENTED";
        ExceptionCode2["Unavailable"] = "UNAVAILABLE";
      })(ExceptionCode || (ExceptionCode = {}));
      CapacitorException = class extends Error {
        constructor(message, code, data) {
          super(message);
          this.message = message;
          this.code = code;
          this.data = data;
        }
      };
      getPlatformId = (win) => {
        var _a, _b;
        if (win === null || win === void 0 ? void 0 : win.androidBridge) {
          return "android";
        } else if ((_b = (_a = win === null || win === void 0 ? void 0 : win.webkit) === null || _a === void 0 ? void 0 : _a.messageHandlers) === null || _b === void 0 ? void 0 : _b.bridge) {
          return "ios";
        } else {
          return "web";
        }
      };
      createCapacitor = (win) => {
        var _a, _b, _c, _d, _e;
        const capCustomPlatform = win.CapacitorCustomPlatform || null;
        const cap = win.Capacitor || {};
        const Plugins2 = cap.Plugins = cap.Plugins || {};
        const capPlatforms = win.CapacitorPlatforms;
        const defaultGetPlatform = () => {
          return capCustomPlatform !== null ? capCustomPlatform.name : getPlatformId(win);
        };
        const getPlatform = ((_a = capPlatforms === null || capPlatforms === void 0 ? void 0 : capPlatforms.currentPlatform) === null || _a === void 0 ? void 0 : _a.getPlatform) || defaultGetPlatform;
        const defaultIsNativePlatform = () => getPlatform() !== "web";
        const isNativePlatform = ((_b = capPlatforms === null || capPlatforms === void 0 ? void 0 : capPlatforms.currentPlatform) === null || _b === void 0 ? void 0 : _b.isNativePlatform) || defaultIsNativePlatform;
        const defaultIsPluginAvailable = (pluginName) => {
          const plugin = registeredPlugins.get(pluginName);
          if (plugin === null || plugin === void 0 ? void 0 : plugin.platforms.has(getPlatform())) {
            return true;
          }
          if (getPluginHeader(pluginName)) {
            return true;
          }
          return false;
        };
        const isPluginAvailable = ((_c = capPlatforms === null || capPlatforms === void 0 ? void 0 : capPlatforms.currentPlatform) === null || _c === void 0 ? void 0 : _c.isPluginAvailable) || defaultIsPluginAvailable;
        const defaultGetPluginHeader = (pluginName) => {
          var _a2;
          return (_a2 = cap.PluginHeaders) === null || _a2 === void 0 ? void 0 : _a2.find((h) => h.name === pluginName);
        };
        const getPluginHeader = ((_d = capPlatforms === null || capPlatforms === void 0 ? void 0 : capPlatforms.currentPlatform) === null || _d === void 0 ? void 0 : _d.getPluginHeader) || defaultGetPluginHeader;
        const handleError = (err) => win.console.error(err);
        const pluginMethodNoop = (_target, prop, pluginName) => {
          return Promise.reject(`${pluginName} does not have an implementation of "${prop}".`);
        };
        const registeredPlugins = /* @__PURE__ */ new Map();
        const defaultRegisterPlugin = (pluginName, jsImplementations = {}) => {
          const registeredPlugin = registeredPlugins.get(pluginName);
          if (registeredPlugin) {
            console.warn(`Capacitor plugin "${pluginName}" already registered. Cannot register plugins twice.`);
            return registeredPlugin.proxy;
          }
          const platform = getPlatform();
          const pluginHeader = getPluginHeader(pluginName);
          let jsImplementation;
          const loadPluginImplementation = async () => {
            if (!jsImplementation && platform in jsImplementations) {
              jsImplementation = typeof jsImplementations[platform] === "function" ? jsImplementation = await jsImplementations[platform]() : jsImplementation = jsImplementations[platform];
            } else if (capCustomPlatform !== null && !jsImplementation && "web" in jsImplementations) {
              jsImplementation = typeof jsImplementations["web"] === "function" ? jsImplementation = await jsImplementations["web"]() : jsImplementation = jsImplementations["web"];
            }
            return jsImplementation;
          };
          const createPluginMethod = (impl, prop) => {
            var _a2, _b2;
            if (pluginHeader) {
              const methodHeader = pluginHeader === null || pluginHeader === void 0 ? void 0 : pluginHeader.methods.find((m) => prop === m.name);
              if (methodHeader) {
                if (methodHeader.rtype === "promise") {
                  return (options) => cap.nativePromise(pluginName, prop.toString(), options);
                } else {
                  return (options, callback) => cap.nativeCallback(pluginName, prop.toString(), options, callback);
                }
              } else if (impl) {
                return (_a2 = impl[prop]) === null || _a2 === void 0 ? void 0 : _a2.bind(impl);
              }
            } else if (impl) {
              return (_b2 = impl[prop]) === null || _b2 === void 0 ? void 0 : _b2.bind(impl);
            } else {
              throw new CapacitorException(`"${pluginName}" plugin is not implemented on ${platform}`, ExceptionCode.Unimplemented);
            }
          };
          const createPluginMethodWrapper = (prop) => {
            let remove;
            const wrapper = (...args) => {
              const p = loadPluginImplementation().then((impl) => {
                const fn = createPluginMethod(impl, prop);
                if (fn) {
                  const p2 = fn(...args);
                  remove = p2 === null || p2 === void 0 ? void 0 : p2.remove;
                  return p2;
                } else {
                  throw new CapacitorException(`"${pluginName}.${prop}()" is not implemented on ${platform}`, ExceptionCode.Unimplemented);
                }
              });
              if (prop === "addListener") {
                p.remove = async () => remove();
              }
              return p;
            };
            wrapper.toString = () => `${prop.toString()}() { [capacitor code] }`;
            Object.defineProperty(wrapper, "name", {
              value: prop,
              writable: false,
              configurable: false
            });
            return wrapper;
          };
          const addListener = createPluginMethodWrapper("addListener");
          const removeListener = createPluginMethodWrapper("removeListener");
          const addListenerNative = (eventName, callback) => {
            const call = addListener({ eventName }, callback);
            const remove = async () => {
              const callbackId = await call;
              removeListener({
                eventName,
                callbackId
              }, callback);
            };
            const p = new Promise((resolve) => call.then(() => resolve({ remove })));
            p.remove = async () => {
              console.warn(`Using addListener() without 'await' is deprecated.`);
              await remove();
            };
            return p;
          };
          const proxy = new Proxy({}, {
            get(_, prop) {
              switch (prop) {
                // https://github.com/facebook/react/issues/20030
                case "$$typeof":
                  return void 0;
                case "toJSON":
                  return () => ({});
                case "addListener":
                  return pluginHeader ? addListenerNative : addListener;
                case "removeListener":
                  return removeListener;
                default:
                  return createPluginMethodWrapper(prop);
              }
            }
          });
          Plugins2[pluginName] = proxy;
          registeredPlugins.set(pluginName, {
            name: pluginName,
            proxy,
            platforms: /* @__PURE__ */ new Set([
              ...Object.keys(jsImplementations),
              ...pluginHeader ? [platform] : []
            ])
          });
          return proxy;
        };
        const registerPlugin2 = ((_e = capPlatforms === null || capPlatforms === void 0 ? void 0 : capPlatforms.currentPlatform) === null || _e === void 0 ? void 0 : _e.registerPlugin) || defaultRegisterPlugin;
        if (!cap.convertFileSrc) {
          cap.convertFileSrc = (filePath) => filePath;
        }
        cap.getPlatform = getPlatform;
        cap.handleError = handleError;
        cap.isNativePlatform = isNativePlatform;
        cap.isPluginAvailable = isPluginAvailable;
        cap.pluginMethodNoop = pluginMethodNoop;
        cap.registerPlugin = registerPlugin2;
        cap.Exception = CapacitorException;
        cap.DEBUG = !!cap.DEBUG;
        cap.isLoggingEnabled = !!cap.isLoggingEnabled;
        cap.platform = cap.getPlatform();
        cap.isNative = cap.isNativePlatform();
        return cap;
      };
      initCapacitorGlobal = (win) => win.Capacitor = createCapacitor(win);
      Capacitor = /* @__PURE__ */ initCapacitorGlobal(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : typeof global !== "undefined" ? global : {});
      registerPlugin = Capacitor.registerPlugin;
      Plugins = Capacitor.Plugins;
      WebPlugin = class {
        constructor(config) {
          this.listeners = {};
          this.retainedEventArguments = {};
          this.windowListeners = {};
          if (config) {
            console.warn(`Capacitor WebPlugin "${config.name}" config object was deprecated in v3 and will be removed in v4.`);
            this.config = config;
          }
        }
        addListener(eventName, listenerFunc) {
          let firstListener = false;
          const listeners = this.listeners[eventName];
          if (!listeners) {
            this.listeners[eventName] = [];
            firstListener = true;
          }
          this.listeners[eventName].push(listenerFunc);
          const windowListener = this.windowListeners[eventName];
          if (windowListener && !windowListener.registered) {
            this.addWindowListener(windowListener);
          }
          if (firstListener) {
            this.sendRetainedArgumentsForEvent(eventName);
          }
          const remove = async () => this.removeListener(eventName, listenerFunc);
          const p = Promise.resolve({ remove });
          return p;
        }
        async removeAllListeners() {
          this.listeners = {};
          for (const listener in this.windowListeners) {
            this.removeWindowListener(this.windowListeners[listener]);
          }
          this.windowListeners = {};
        }
        notifyListeners(eventName, data, retainUntilConsumed) {
          const listeners = this.listeners[eventName];
          if (!listeners) {
            if (retainUntilConsumed) {
              let args = this.retainedEventArguments[eventName];
              if (!args) {
                args = [];
              }
              args.push(data);
              this.retainedEventArguments[eventName] = args;
            }
            return;
          }
          listeners.forEach((listener) => listener(data));
        }
        hasListeners(eventName) {
          return !!this.listeners[eventName].length;
        }
        registerWindowListener(windowEventName, pluginEventName) {
          this.windowListeners[pluginEventName] = {
            registered: false,
            windowEventName,
            pluginEventName,
            handler: (event) => {
              this.notifyListeners(pluginEventName, event);
            }
          };
        }
        unimplemented(msg = "not implemented") {
          return new Capacitor.Exception(msg, ExceptionCode.Unimplemented);
        }
        unavailable(msg = "not available") {
          return new Capacitor.Exception(msg, ExceptionCode.Unavailable);
        }
        async removeListener(eventName, listenerFunc) {
          const listeners = this.listeners[eventName];
          if (!listeners) {
            return;
          }
          const index = listeners.indexOf(listenerFunc);
          this.listeners[eventName].splice(index, 1);
          if (!this.listeners[eventName].length) {
            this.removeWindowListener(this.windowListeners[eventName]);
          }
        }
        addWindowListener(handle) {
          window.addEventListener(handle.windowEventName, handle.handler);
          handle.registered = true;
        }
        removeWindowListener(handle) {
          if (!handle) {
            return;
          }
          window.removeEventListener(handle.windowEventName, handle.handler);
          handle.registered = false;
        }
        sendRetainedArgumentsForEvent(eventName) {
          const args = this.retainedEventArguments[eventName];
          if (!args) {
            return;
          }
          delete this.retainedEventArguments[eventName];
          args.forEach((arg) => {
            this.notifyListeners(eventName, arg);
          });
        }
      };
      encode = (str) => encodeURIComponent(str).replace(/%(2[346B]|5E|60|7C)/g, decodeURIComponent).replace(/[()]/g, escape);
      decode = (str) => str.replace(/(%[\dA-F]{2})+/gi, decodeURIComponent);
      CapacitorCookiesPluginWeb = class extends WebPlugin {
        async getCookies() {
          const cookies = document.cookie;
          const cookieMap = {};
          cookies.split(";").forEach((cookie) => {
            if (cookie.length <= 0)
              return;
            let [key2, value] = cookie.replace(/=/, "CAP_COOKIE").split("CAP_COOKIE");
            key2 = decode(key2).trim();
            value = decode(value).trim();
            cookieMap[key2] = value;
          });
          return cookieMap;
        }
        async setCookie(options) {
          try {
            const encodedKey = encode(options.key);
            const encodedValue = encode(options.value);
            const expires = `; expires=${(options.expires || "").replace("expires=", "")}`;
            const path = (options.path || "/").replace("path=", "");
            const domain = options.url != null && options.url.length > 0 ? `domain=${options.url}` : "";
            document.cookie = `${encodedKey}=${encodedValue || ""}${expires}; path=${path}; ${domain};`;
          } catch (error2) {
            return Promise.reject(error2);
          }
        }
        async deleteCookie(options) {
          try {
            document.cookie = `${options.key}=; Max-Age=0`;
          } catch (error2) {
            return Promise.reject(error2);
          }
        }
        async clearCookies() {
          try {
            const cookies = document.cookie.split(";") || [];
            for (const cookie of cookies) {
              document.cookie = cookie.replace(/^ +/, "").replace(/=.*/, `=;expires=${(/* @__PURE__ */ new Date()).toUTCString()};path=/`);
            }
          } catch (error2) {
            return Promise.reject(error2);
          }
        }
        async clearAllCookies() {
          try {
            await this.clearCookies();
          } catch (error2) {
            return Promise.reject(error2);
          }
        }
      };
      CapacitorCookies = registerPlugin("CapacitorCookies", {
        web: () => new CapacitorCookiesPluginWeb()
      });
      readBlobAsBase64 = async (blob) => new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const base64String = reader.result;
          resolve(base64String.indexOf(",") >= 0 ? base64String.split(",")[1] : base64String);
        };
        reader.onerror = (error2) => reject(error2);
        reader.readAsDataURL(blob);
      });
      normalizeHttpHeaders = (headers = {}) => {
        const originalKeys = Object.keys(headers);
        const loweredKeys = Object.keys(headers).map((k) => k.toLocaleLowerCase());
        const normalized = loweredKeys.reduce((acc, key2, index) => {
          acc[key2] = headers[originalKeys[index]];
          return acc;
        }, {});
        return normalized;
      };
      buildUrlParams = (params, shouldEncode = true) => {
        if (!params)
          return null;
        const output = Object.entries(params).reduce((accumulator, entry) => {
          const [key2, value] = entry;
          let encodedValue;
          let item;
          if (Array.isArray(value)) {
            item = "";
            value.forEach((str) => {
              encodedValue = shouldEncode ? encodeURIComponent(str) : str;
              item += `${key2}=${encodedValue}&`;
            });
            item.slice(0, -1);
          } else {
            encodedValue = shouldEncode ? encodeURIComponent(value) : value;
            item = `${key2}=${encodedValue}`;
          }
          return `${accumulator}&${item}`;
        }, "");
        return output.substr(1);
      };
      buildRequestInit = (options, extra = {}) => {
        const output = Object.assign({ method: options.method || "GET", headers: options.headers }, extra);
        const headers = normalizeHttpHeaders(options.headers);
        const type = headers["content-type"] || "";
        if (typeof options.data === "string") {
          output.body = options.data;
        } else if (type.includes("application/x-www-form-urlencoded")) {
          const params = new URLSearchParams();
          for (const [key2, value] of Object.entries(options.data || {})) {
            params.set(key2, value);
          }
          output.body = params.toString();
        } else if (type.includes("multipart/form-data") || options.data instanceof FormData) {
          const form = new FormData();
          if (options.data instanceof FormData) {
            options.data.forEach((value, key2) => {
              form.append(key2, value);
            });
          } else {
            for (const key2 of Object.keys(options.data)) {
              form.append(key2, options.data[key2]);
            }
          }
          output.body = form;
          const headers2 = new Headers(output.headers);
          headers2.delete("content-type");
          output.headers = headers2;
        } else if (type.includes("application/json") || typeof options.data === "object") {
          output.body = JSON.stringify(options.data);
        }
        return output;
      };
      CapacitorHttpPluginWeb = class extends WebPlugin {
        /**
         * Perform an Http request given a set of options
         * @param options Options to build the HTTP request
         */
        async request(options) {
          const requestInit = buildRequestInit(options, options.webFetchExtra);
          const urlParams = buildUrlParams(options.params, options.shouldEncodeUrlParams);
          const url = urlParams ? `${options.url}?${urlParams}` : options.url;
          const response = await fetch(url, requestInit);
          const contentType = response.headers.get("content-type") || "";
          let { responseType = "text" } = response.ok ? options : {};
          if (contentType.includes("application/json")) {
            responseType = "json";
          }
          let data;
          let blob;
          switch (responseType) {
            case "arraybuffer":
            case "blob":
              blob = await response.blob();
              data = await readBlobAsBase64(blob);
              break;
            case "json":
              data = await response.json();
              break;
            case "document":
            case "text":
            default:
              data = await response.text();
          }
          const headers = {};
          response.headers.forEach((value, key2) => {
            headers[key2] = value;
          });
          return {
            data,
            headers,
            status: response.status,
            url: response.url
          };
        }
        /**
         * Perform an Http GET request given a set of options
         * @param options Options to build the HTTP request
         */
        async get(options) {
          return this.request(Object.assign(Object.assign({}, options), { method: "GET" }));
        }
        /**
         * Perform an Http POST request given a set of options
         * @param options Options to build the HTTP request
         */
        async post(options) {
          return this.request(Object.assign(Object.assign({}, options), { method: "POST" }));
        }
        /**
         * Perform an Http PUT request given a set of options
         * @param options Options to build the HTTP request
         */
        async put(options) {
          return this.request(Object.assign(Object.assign({}, options), { method: "PUT" }));
        }
        /**
         * Perform an Http PATCH request given a set of options
         * @param options Options to build the HTTP request
         */
        async patch(options) {
          return this.request(Object.assign(Object.assign({}, options), { method: "PATCH" }));
        }
        /**
         * Perform an Http DELETE request given a set of options
         * @param options Options to build the HTTP request
         */
        async delete(options) {
          return this.request(Object.assign(Object.assign({}, options), { method: "DELETE" }));
        }
      };
      CapacitorHttp = registerPlugin("CapacitorHttp", {
        web: () => new CapacitorHttpPluginWeb()
      });
    }
  });

  // node_modules/@capacitor-mlkit/barcode-scanning/dist/esm/web.js
  var web_exports = {};
  __export(web_exports, {
    BarcodeScannerWeb: () => BarcodeScannerWeb
  });
  var BarcodeScannerWeb;
  var init_web = __esm({
    "node_modules/@capacitor-mlkit/barcode-scanning/dist/esm/web.js"() {
      init_dist();
      BarcodeScannerWeb = class extends WebPlugin {
        async startScan(_options) {
          throw this.createUnavailableException();
        }
        async stopScan() {
          throw this.createUnavailableException();
        }
        async readBarcodesFromImage(_options) {
          throw this.createUnavailableException();
        }
        async scan() {
          throw this.createUnavailableException();
        }
        async isSupported() {
          throw this.createUnavailableException();
        }
        async enableTorch() {
          throw this.createUnavailableException();
        }
        async disableTorch() {
          throw this.createUnavailableException();
        }
        async toggleTorch() {
          throw this.createUnavailableException();
        }
        async isTorchEnabled() {
          throw this.createUnavailableException();
        }
        async isTorchAvailable() {
          throw this.createUnavailableException();
        }
        async setZoomRatio(_options) {
          throw this.createUnavailableException();
        }
        async getZoomRatio() {
          throw this.createUnavailableException();
        }
        async getMinZoomRatio() {
          throw this.createUnavailableException();
        }
        async getMaxZoomRatio() {
          throw this.createUnavailableException();
        }
        async openSettings() {
          throw this.createUnavailableException();
        }
        async isGoogleBarcodeScannerModuleAvailable() {
          throw this.createUnavailableException();
        }
        async installGoogleBarcodeScannerModule() {
          throw this.createUnavailableException();
        }
        async checkPermissions() {
          throw this.createUnavailableException();
        }
        async requestPermissions() {
          throw this.createUnavailableException();
        }
        createUnavailableException() {
          return new CapacitorException("This Barcode Scanner plugin method is not available on this platform.", ExceptionCode.Unavailable);
        }
      };
    }
  });

  // node_modules/@capacitor-mlkit/barcode-scanning/dist/esm/index.js
  init_dist();

  // node_modules/@capacitor-mlkit/barcode-scanning/dist/esm/definitions.js
  var BarcodeFormat;
  (function(BarcodeFormat2) {
    BarcodeFormat2["Aztec"] = "AZTEC";
    BarcodeFormat2["Codabar"] = "CODABAR";
    BarcodeFormat2["Code39"] = "CODE_39";
    BarcodeFormat2["Code93"] = "CODE_93";
    BarcodeFormat2["Code128"] = "CODE_128";
    BarcodeFormat2["DataMatrix"] = "DATA_MATRIX";
    BarcodeFormat2["Ean8"] = "EAN_8";
    BarcodeFormat2["Ean13"] = "EAN_13";
    BarcodeFormat2["Itf"] = "ITF";
    BarcodeFormat2["Pdf417"] = "PDF_417";
    BarcodeFormat2["QrCode"] = "QR_CODE";
    BarcodeFormat2["UpcA"] = "UPC_A";
    BarcodeFormat2["UpcE"] = "UPC_E";
  })(BarcodeFormat || (BarcodeFormat = {}));
  var BarcodeValueType;
  (function(BarcodeValueType2) {
    BarcodeValueType2["CalendarEvent"] = "CALENDAR_EVENT";
    BarcodeValueType2["ContactInfo"] = "CONTACT_INFO";
    BarcodeValueType2["DriversLicense"] = "DRIVERS_LICENSE";
    BarcodeValueType2["Email"] = "EMAIL";
    BarcodeValueType2["Geo"] = "GEO";
    BarcodeValueType2["Isbn"] = "ISBN";
    BarcodeValueType2["Phone"] = "PHONE";
    BarcodeValueType2["Product"] = "PRODUCT";
    BarcodeValueType2["Sms"] = "SMS";
    BarcodeValueType2["Text"] = "TEXT";
    BarcodeValueType2["Url"] = "URL";
    BarcodeValueType2["Wifi"] = "WIFI";
    BarcodeValueType2["Unknown"] = "UNKNOWN";
  })(BarcodeValueType || (BarcodeValueType = {}));
  var LensFacing;
  (function(LensFacing2) {
    LensFacing2["Front"] = "FRONT";
    LensFacing2["Back"] = "BACK";
  })(LensFacing || (LensFacing = {}));
  var GoogleBarcodeScannerModuleInstallState;
  (function(GoogleBarcodeScannerModuleInstallState2) {
    GoogleBarcodeScannerModuleInstallState2[GoogleBarcodeScannerModuleInstallState2["UNKNOWN"] = 0] = "UNKNOWN";
    GoogleBarcodeScannerModuleInstallState2[GoogleBarcodeScannerModuleInstallState2["PENDING"] = 1] = "PENDING";
    GoogleBarcodeScannerModuleInstallState2[GoogleBarcodeScannerModuleInstallState2["DOWNLOADING"] = 2] = "DOWNLOADING";
    GoogleBarcodeScannerModuleInstallState2[GoogleBarcodeScannerModuleInstallState2["CANCELED"] = 3] = "CANCELED";
    GoogleBarcodeScannerModuleInstallState2[GoogleBarcodeScannerModuleInstallState2["COMPLETED"] = 4] = "COMPLETED";
    GoogleBarcodeScannerModuleInstallState2[GoogleBarcodeScannerModuleInstallState2["FAILED"] = 5] = "FAILED";
    GoogleBarcodeScannerModuleInstallState2[GoogleBarcodeScannerModuleInstallState2["INSTALLING"] = 6] = "INSTALLING";
    GoogleBarcodeScannerModuleInstallState2[GoogleBarcodeScannerModuleInstallState2["DOWNLOAD_PAUSED"] = 7] = "DOWNLOAD_PAUSED";
  })(GoogleBarcodeScannerModuleInstallState || (GoogleBarcodeScannerModuleInstallState = {}));

  // node_modules/@capacitor-mlkit/barcode-scanning/dist/esm/index.js
  var BarcodeScanner = registerPlugin("BarcodeScanner", {
    web: () => Promise.resolve().then(() => (init_web(), web_exports)).then((m) => new m.BarcodeScannerWeb())
  });

  // src/app.js
  var input = document.querySelector("#url");
  var error = document.querySelector("#error");
  var recent = document.querySelector("#recent");
  var list = document.querySelector("#recentList");
  var scanButton = document.querySelector("#scan");
  var key = "autorip.server.urls";
  function urls() {
    try {
      return JSON.parse(localStorage.getItem(key) || "[]").filter((x) => typeof x === "string");
    } catch {
      return [];
    }
  }
  function render() {
    const items = urls();
    recent.hidden = !items.length;
    list.replaceChildren();
    items.forEach((value) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.textContent = value;
      button.onclick = () => {
        input.value = value;
        connect(value);
      };
      li.appendChild(button);
      list.appendChild(li);
    });
  }
  function parseServerUrl(value) {
    const text = value.trim();
    if (!text || /[?#]/.test(text)) throw new Error("query-fragment");
    const url = new URL(text);
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash) throw new Error("invalid-url");
    return url;
  }
  function connect(value = input.value) {
    error.textContent = "";
    let url;
    try {
      url = parseServerUrl(value);
    } catch {
      error.textContent = "Informe um endere\xE7o HTTP(S) v\xE1lido, sem usu\xE1rio, senha, query ou fragmento.";
      return false;
    }
    const clean = url.href.replace(/\/$/, "");
    const items = [clean, ...urls().filter((x) => x !== clean)].slice(0, 5);
    localStorage.setItem(key, JSON.stringify(items));
    location.replace(`${clean}/`);
    return true;
  }
  async function scanQr() {
    error.textContent = "";
    scanButton.disabled = true;
    try {
      const supported = await BarcodeScanner.isSupported();
      if (!supported.supported) {
        error.textContent = "Este dispositivo n\xE3o tem c\xE2mera compat\xEDvel para ler QR.";
        return;
      }
      let permission = await BarcodeScanner.checkPermissions();
      if (permission.camera !== "granted") permission = await BarcodeScanner.requestPermissions();
      if (permission.camera !== "granted") {
        error.textContent = "Permiss\xE3o da c\xE2mera negada. Autorize a c\xE2mera nas configura\xE7\xF5es ou informe o endere\xE7o manualmente.";
        return;
      }
      const result = await BarcodeScanner.scan({ formats: [BarcodeFormat.QrCode] });
      const value = result.barcodes?.find((barcode) => barcode.format === BarcodeFormat.QrCode && barcode.rawValue)?.rawValue;
      if (!value) return;
      let url;
      try {
        url = parseServerUrl(value);
      } catch {
        error.textContent = "O QR n\xE3o cont\xE9m um endere\xE7o HTTP(S) v\xE1lido. S\xE3o aceitos apenas URLs sem usu\xE1rio, senha, query ou fragmento.";
        return;
      }
      input.value = url.href;
      connect(url.href);
    } catch (cause) {
      const message = String(cause?.message || cause || "");
      if (/cancel|dismiss|canceled/i.test(message)) return;
      error.textContent = "N\xE3o foi poss\xEDvel abrir a c\xE2mera. Voc\xEA ainda pode informar o endere\xE7o manualmente.";
    } finally {
      scanButton.disabled = false;
    }
  }
  document.querySelector("#connect").onclick = () => connect();
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") connect();
  });
  scanButton.onclick = scanQr;
  render();
})();
/*! Bundled license information:

@capacitor/core/dist/index.js:
  (*! Capacitor: https://capacitorjs.com/ - MIT License *)
*/
