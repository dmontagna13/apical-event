declare namespace JSX {
  interface Element {}
  interface IntrinsicAttributes {
    key?: string | number;
  }
  interface IntrinsicElements {
    [elemName: string]: Record<string, unknown>;
  }
}

declare module "react" {
  export type ReactNode =
    | JSX.Element
    | string
    | number
    | boolean
    | null
    | undefined
    | ReactNode[];

  export interface FunctionComponent<P = Record<string, unknown>> {
    (props: P & { children?: ReactNode }): JSX.Element | null;
  }

  export type FC<P = Record<string, unknown>> = FunctionComponent<P>;
  export type ComponentType<P = Record<string, unknown>> = FunctionComponent<P>;

  export class Component<P = Record<string, unknown>, S = Record<string, unknown>> {
    constructor(props: P);
    props: P;
    state: S;
    setState(state: Partial<S>): void;
    render(): ReactNode;
  }

  export interface Context<T> {
    Provider: FunctionComponent<{ value: T; children?: ReactNode }>;
    Consumer: FunctionComponent<{ children: (value: T) => ReactNode }>;
  }

  export function createContext<T>(defaultValue: T): Context<T>;
  export function useContext<T>(context: Context<T>): T;

  export function useState<S>(
    initialState: S | (() => S)
  ): [S, (value: S | ((prev: S) => S)) => void];
  export function useEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void;
  export function useMemo<T>(factory: () => T, deps: readonly unknown[]): T;
  export function useCallback<T>(callback: T, deps: readonly unknown[]): T;

  export const StrictMode: FunctionComponent<{ children?: ReactNode }>;

  const React: {
    StrictMode: typeof StrictMode;
    Component: typeof Component;
  };
  export default React;
}

declare module "react-dom/client" {
  import type { ReactNode } from "react";

  export interface Root {
    render(children: ReactNode): void;
  }

  export function createRoot(container: Element | DocumentFragment): Root;
}

declare module "react/jsx-runtime" {
  export const jsx: unknown;
  export const jsxs: unknown;
  export const Fragment: unknown;
}
