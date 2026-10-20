components {
  id: "mesh"
  component: "/main/platforms/burning_sticky/platform.mesh"
}
components {
  id: "mesh_sticky"
  component: "/main/platforms/burning/platform_sticky.mesh"
}
components {
  id: "collision_object"
  component: "/main/platforms/platform.collisionobject"
}
components {
  id: "bend"
  component: "/main/platforms/platform.script"
}
components {
  id: "burning"
  component: "/main/platforms/burning/burning.script"
  properties {
    id: "burning"
    type: PROPERTY_TYPE_NUMBER
    value: "1"
  }
  properties {
    id: "sticky_after"
    type: PROPERTY_TYPE_NUMBER
    value: "1"
  }
}
components {
  id: "sticky"
  component: "/main/platforms/sticky/sticky.script"
  properties {
    id: "sticky"
    type: PROPERTY_TYPE_NUMBER
    value: "1"
  }
}
components {
  id: "slope"
  component: "/main/platforms/sloped/sloped.script"
  properties {
    id: "direction"
    type: PROPERTY_TYPE_NUMBER
    value: "0"
  }
}
