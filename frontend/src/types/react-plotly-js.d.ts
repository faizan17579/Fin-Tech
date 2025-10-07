declare module 'react-plotly.js' {
  import * as React from 'react';
  export interface PlotParams {
    data: any[];
    layout?: any;
    config?: any;
    style?: React.CSSProperties;
    useResizeHandler?: boolean;
    onInitialized?: (figure: any) => void;
    onUpdate?: (figure: any) => void;
  }
  export default class Plot extends React.Component<PlotParams> {}
}
